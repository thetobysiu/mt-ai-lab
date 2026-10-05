"""Inventory scripted floor events (afterBattle / NPC events) that the engine does not model."""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FLOORS = Path(__file__).resolve().parents[1] / "data" / "games" / "24" / "project" / "floors"


def _section(text: str, key: str):
    m = re.search(r'"%s": (\{.*?\n    \}),\n' % key, text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {"_unparsed": True}


def _walk(o, acc):
    if isinstance(o, dict):
        t = o.get("type")
        if t and t not in ("playSound", "sleep", "setText", "vibrate", "animate"):
            detail = o.get("number", o.get("name", o.get("condition", o.get("loc", ""))))
            acc.append(f"{t}:{str(detail)[:40]}")
        for v in o.values():
            _walk(v, acc)
    elif isinstance(o, list):
        for v in o:
            _walk(v, acc)


for fid in sys.argv[1:] or [f"MT{i}" for i in range(0, 23)] + ["MT23w", "MT23e", "MT23s"]:
    p = FLOORS / f"{fid}.js"
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8")
    for key in ("events", "afterBattle", "afterGetItem", "afterOpenDoor", "firstArrive", "eachArrive"):
        if key in ("firstArrive", "eachArrive"):
            m = re.search(r'"%s": (\[.*?\n    \]),\n' % key, text, re.S)
            try:
                sec = json.loads(m.group(1)) if m else []
            except json.JSONDecodeError:
                sec = []
        else:
            sec = _section(text, key)
        acc: list[str] = []
        _walk(sec, acc)
        if acc:
            print(f"{fid:6s} {key:13s} {acc[:18]}")
