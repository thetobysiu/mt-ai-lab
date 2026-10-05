"""Probe thinking/no-think behaviour, latency and structured-output support for a model."""
from __future__ import annotations
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from openai import OpenAI

client = OpenAI(api_key=os.environ["SAIA_API_KEY"],
                base_url=os.environ.get("SAIA_BASE_URL"), timeout=300)
MODELS = sys.argv[1:] or ["qwen3.6-35b-a3b", "qwen3.8-27b"]


def reasoning_of(message) -> str:
    r = getattr(message, "reasoning", None)
    if not r:
        r = (getattr(message, "model_extra", None) or {}).get("reasoning", "")
    return r or ""


def call(model, **kw):
    t0 = time.time()
    try:
        resp = client.chat.completions.create(model=model, temperature=0.0, **kw)
        ch = resp.choices[0]
        return dict(ok=True, s=time.time() - t0, finish=ch.finish_reason,
                    content=ch.message.content, rlen=len(reasoning_of(ch.message)))
    except Exception as e:
        return dict(ok=False, s=time.time() - t0, err=f"{type(e).__name__}: {str(e)[:90]}")


for m in MODELS:
    print(f"\n=== {m} ===")
    for tag, msg, mt in (("think/512", "Reply with the single word OK", 512),
                         ("think/4096", "Reply with the single word OK", 4096),
                         ("no_think/512", "Reply with the single word OK\n/no_think", 512)):
        r = call(m, messages=[{"role": "user", "content": msg}], max_tokens=mt)
        if r["ok"]:
            print(f"  {tag:13s} {r['s']:5.1f}s finish={r['finish']:8s} "
                  f"content={str(r['content'])[:30]!r} reasoning={r['rlen']}c")
        else:
            print(f"  {tag:13s} {r['s']:5.1f}s {r['err']}")

    schema = {"type": "object",
              "properties": {"action_id": {"type": "integer", "enum": [1, 2, 3]}},
              "required": ["action_id"], "additionalProperties": False}
    r = call(m, messages=[{"role": "user", "content": "Pick action 2.\n/no_think"}], max_tokens=256,
             response_format={"type": "json_schema",
                              "json_schema": {"name": "c", "schema": schema, "strict": True}})
    print(f"  json_schema   {r['s']:5.1f}s " + (f"content={str(r['content'])[:60]!r}" if r["ok"] else r["err"]))

    r = call(m, messages=[{"role": "user", "content": "Pick action 2.\n/no_think"}], max_tokens=256,
             extra_body={"guided_choice": ["1", "2", "3"]})
    print(f"  guided_choice {r['s']:5.1f}s " + (f"content={str(r['content'])[:60]!r}" if r["ok"] else r["err"]))
