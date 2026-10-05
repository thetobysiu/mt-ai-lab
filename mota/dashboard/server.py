"""
Magic Tower AI Lab dashboard — FastAPI application factory.

Routers live in mota/dashboard/api/*.py; this module only assembles them, serves the
Next.js static export (web/out) with an SPA fallback, and picks a free port.

Usage:
    python -m mota.dashboard
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
from dotenv import load_dotenv

from .api.paths import GEPA_ROOT, PROJECT_ROOT, WEB_OUT

if (GEPA_ROOT / ".env").exists():
    load_dotenv(GEPA_ROOT / ".env")


def _guarded(base: Path, rel: str) -> Path | None:
    """Resolve rel under base; None if it escapes base (path traversal guard)."""
    target = (base / rel).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


async def _serve_web(request: Request):
    """Static Next.js export with SPA-style fallbacks (`/play/` -> play/index.html)."""
    rel = request.path_params.get("filename", "")
    if not WEB_OUT.exists():
        return JSONResponse(
            {"error": "web build missing", "hint": "run scripts/build_web.ps1 (npm ci && npm run build in mota/dashboard/web)"},
            status_code=503,
        )
    target = _guarded(WEB_OUT, rel)
    if target is None:
        raise HTTPException(status_code=403)
    if target.is_file():
        return FileResponse(target)
    if target.is_dir() and (target / "index.html").is_file():
        return FileResponse(target / "index.html", headers={"Cache-Control": "no-cache"})
    html = target.with_suffix(".html")
    if html.is_file():
        return FileResponse(html, headers={"Cache-Control": "no-cache"})
    return FileResponse(WEB_OUT / "index.html", headers={"Cache-Control": "no-cache"})


def create_app() -> FastAPI:
    from contextlib import asynccontextmanager
    from .api import ROUTERS
    from .api.ws import router as ws_router
    from .watcher import watcher

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        import threading
        from .api.latency import warm_cache
        await watcher.start()
        threading.Thread(target=warm_cache, name="latency-warm", daemon=True).start()
        try:
            yield
        finally:
            await watcher.stop()

    app = FastAPI(title="Magic Tower AI Lab", lifespan=lifespan)
    # `next dev` (port 3000) talks to this API during front-end development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in ROUTERS:
        app.include_router(r)
    app.include_router(ws_router)

    app.add_api_route("/", _serve_web, methods=["GET", "HEAD"], include_in_schema=False)
    app.add_api_route("/{filename:path}", _serve_web, methods=["GET", "HEAD"], include_in_schema=False)
    return app


def _port_is_free(port: int) -> bool:
    """uvicorn.run() swallows bind errors, so probe the port ourselves."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    start_port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    max_tries = int(os.environ.get("DASHBOARD_PORT_TRIES", "20"))

    for offset in range(max_tries):
        port = start_port + offset
        if not _port_is_free(port):
            print(f"Port {port} busy, trying {port + 1}...")
            continue
        print(f"Magic Tower AI Lab: http://localhost:{port}")
        if not WEB_OUT.exists():
            print("  web build missing -> run scripts\\build_web.ps1 (npm ci && npm run build)")
        # Windows resolves "localhost" to ::1 first; an IPv4-only bind costs every request a ~2 s
        # IPv6 connect timeout before the fallback. Serve both stacks.
        config = uvicorn.Config(app, port=port, log_level="info")
        server = uvicorn.Server(config)
        import socket
        socks = []
        for fam, addr in ((socket.AF_INET6, "::1"), (socket.AF_INET, "127.0.0.1")):
            try:
                s = socket.socket(fam, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if fam == socket.AF_INET6:
                    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                s.bind((addr, port))
                s.listen(2048)
                socks.append(s)
            except OSError:
                pass
        import asyncio
        asyncio.run(server.serve(sockets=socks) if socks else server.serve())
        return

    raise OSError(f"No free port in range {start_port}-{start_port + max_tries - 1}")


app = create_app()


if __name__ == "__main__":
    main()
