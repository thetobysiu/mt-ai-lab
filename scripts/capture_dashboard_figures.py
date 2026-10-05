"""
Capture dashboard screenshots for the thesis (Chapter 4 §4.7) — Next.js UI.

Requires a running dashboard (python -m mota.dashboard) with a built front end
(scripts/build_web.ps1) and the `playwright` package; uses the locally installed Microsoft
Edge, so no browser download. Heuristic / BFS runs only — no LLM API calls.

    python scripts/capture_dashboard_figures.py [--url http://localhost:8080] [--out docs/images]

Figures written (PNG):
    fig_dash_01_overview_simple_map.png       /play?floor=simple: condition form + floor map preview
    fig_dash_02_heuristic_simple_timeline.png  heuristic episode on simple: map, scrubber, timeline, two-tier score
    fig_dash_03_java_bfs_replay_simple.png    Java BFS oracle replay (HP=13 optimal)
    fig_dash_04_llm_run_log_cot.png           /logs: stored LLM kill replayed, reasoning expanded
    fig_dash_05_prompt_versions.png           prompt editor with version store
    fig_dash_06_gepa_history.png              /gepa: a study run's iterations, prompt diff, teacher diagnosis
    fig_dash_07_experiments_results.png       /experiments: thesis catalog (thesis result + re-run with own key)
    fig_dash_08_multi_floor_heuristic.png     tower heuristic MT0->MT4 with floor transitions
    fig_dash_09_manual_mode_actions.png       manual mode: engine-enumerated actions for a human
    fig_dash_10_live_jobs.png                 /live: job registry with a running/finished job selected
    fig_dash_11_game_textures.png             /maps: MT5 drawn with the original game's sprites
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

VIEWPORT = {"width": 1600, "height": 1000}


def wait_result(page: Page, timeout_ms: int = 180_000):
    # the footer renders score-outcome once the result event arrived; log_saved / done follow within a second
    page.wait_for_selector('[data-testid="score-outcome"]', state="attached", timeout=timeout_ms)
    time.sleep(1.2)


def shot(page: Page, out: Path, name: str, full: bool = False):
    page.mouse.move(VIEWPORT["width"] - 2, VIEWPORT["height"] - 2)  # park the cursor: no map tooltip in the figure
    time.sleep(0.2)
    path = out / name
    page.screenshot(path=str(path), full_page=full)
    print(f"  saved {path.name}")


def goto(page: Page, base: str, path: str):
    page.goto(f"{base}{path}", wait_until="networkidle")
    time.sleep(0.6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "docs" / "images"))
    ap.add_argument("--channel", default="msedge", help="playwright browser channel (msedge | chrome)")
    ap.add_argument("--only", type=int, nargs="*", help="figure numbers to capture (default all)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = args.url.rstrip("/")
    want = set(args.only) if args.only else set(range(1, 12))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1.5)

        if want & {1, 2, 3}:
            # 1. Play page with the simple floor preview
            goto(page, base, "/play/?floor=simple")
            page.wait_for_selector('[data-testid="floor-map"]')
            page.wait_for_function("() => document.querySelectorAll('[data-testid=\"preset-select\"] option').length > 1")
            time.sleep(0.5)
            if 1 in want:
                shot(page, out, "fig_dash_01_overview_simple_map.png")

        if 2 in want:
            # 2. Heuristic episode -> timeline + two-tier score footer
            page.get_by_test_id("btn-heuristic").click()
            wait_result(page)
            shot(page, out, "fig_dash_02_heuristic_simple_timeline.png")

        if 3 in want:
            # 3. Java BFS oracle replay
            page.get_by_test_id("btn-java-bfs").click()
            wait_result(page, timeout_ms=240_000)
            shot(page, out, "fig_dash_03_java_bfs_replay_simple.png")

        if 4 in want:
            # 4. Stored LLM run log with CoT (prefer a success on simple)
            goto(page, base, "/logs/")
            page.select_option('[data-testid="log-mode-filter"]', "llm")
            time.sleep(1.5)
            rows = page.locator('[data-testid="log-row"]', has_text="✓")
            if rows.count() == 0:
                rows = page.locator('[data-testid="log-row"]')
            if rows.count() > 0:
                rows.first.click()
                page.wait_for_selector('[data-testid="log-filename"]', timeout=60_000)
                time.sleep(2.0)
                page.locator('[data-testid="run-view"] input[type=checkbox]').first.check()  # expand CoT
                time.sleep(0.8)
                shot(page, out, "fig_dash_04_llm_run_log_cot.png")
            else:
                print("  (no LLM run log found — skipping fig 04)")

        if 5 in want:
            # 5. Prompt editor with versions
            goto(page, base, "/play/?floor=simple")
            page.get_by_test_id("btn-toggle-prompt").click()
            page.wait_for_selector('[data-testid="prompt-editor"]')
            page.locator('[data-testid="prompt-editor"] details summary').last.click()
            time.sleep(0.6)
            shot(page, out, "fig_dash_05_prompt_versions.png")

        if 6 in want:
            # 6. GEPA: one study run, iteration by iteration, with the prompt diff and teacher diagnosis
            goto(page, base, "/gepa/")
            page.wait_for_selector('[data-testid="gepa-run-row"]', timeout=30_000)
            page.locator('[data-testid="gepa-run-row"]', has_text="gs_dsv4flash_full").click()
            page.wait_for_selector('[data-testid="gepa-iterations"]', timeout=30_000)
            page.locator('[data-testid="gepa-iter-open"]').nth(1).click()
            time.sleep(1.0)
            shot(page, out, "fig_dash_06_gepa_history.png")

        if 7 in want:
            # 7. Experiments: the thesis catalog with thesis results and the re-run panel
            goto(page, base, "/experiments/")
            page.get_by_test_id("tab-catalog").click()
            page.wait_for_selector('[data-testid="catalog-entry"]', timeout=30_000)
            time.sleep(0.5)
            shot(page, out, "fig_dash_07_experiments_results.png")

        if 8 in want:
            # 8. Tower heuristic MT0 -> MT4
            goto(page, base, "/play/?floor=mota24")
            page.wait_for_selector('[data-testid="end-floor"]')
            page.wait_for_function("() => document.querySelectorAll('[data-testid=\"end-floor\"] option').length > 1")
            page.select_option('[data-testid="end-floor"]', "MT4")
            time.sleep(0.3)
            page.get_by_test_id("btn-heuristic").click()
            wait_result(page, timeout_ms=240_000)
            shot(page, out, "fig_dash_08_multi_floor_heuristic.png")

        if 9 in want:
            # 9. Manual mode on the simple floor
            goto(page, base, "/play/?floor=simple")
            page.get_by_test_id("btn-manual").click()
            page.wait_for_selector('[data-testid="manual-actions"]', timeout=30_000)
            time.sleep(0.8)
            shot(page, out, "fig_dash_09_manual_mode_actions.png")
            try:
                page.get_by_role("button", name="End manual").click(timeout=2000)
            except Exception:
                pass

        if 10 in want:
            # 10. Live jobs (the runs above are registered as ui-eval jobs)
            goto(page, base, "/live/")
            page.wait_for_selector('[data-testid="job-row"]', timeout=30_000)
            page.locator('[data-testid="job-row"]').first.click()
            page.wait_for_selector('[data-testid="selected-job"]')
            time.sleep(2.5)
            shot(page, out, "fig_dash_10_live_jobs.png")

        if 11 in want:
            # 11. Maps page, MT5 in the game-texture view (original game sprites)
            goto(page, base, "/maps/?floor=MT5")
            page.get_by_test_id("maps-tab-tower").click()
            page.locator('[data-testid="floor-item"][data-floor="MT5"]').click()
            page.select_option('[data-testid="map-skin"]', "game")
            page.wait_for_selector('[data-testid="floor-map"][data-skin="game"] [data-x]', timeout=30_000)
            time.sleep(1.0)
            shot(page, out, "fig_dash_11_game_textures.png")
            page.select_option('[data-testid="map-skin"]', "classic")

        browser.close()
    print("done ->", out)


if __name__ == "__main__":
    main()
