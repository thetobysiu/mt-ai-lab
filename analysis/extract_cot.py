"""Dump the model's reasoning at one decision of a stored episode (thesis Appendix J).

usage: python scratch/extract_cot.py <result-label> <run 1-based> <turn|first|action-substring>
Writes scratch/_cot/<label>_r<run>_t<turn>.txt and prints a one-line summary.
"""
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
label, run, sel = sys.argv[1], int(sys.argv[2]), sys.argv[3]
rec = json.load(open(ROOT / "results" / "reliability" / f"{label}.json", encoding="utf-8"))["runs"][run - 1]
log = json.load(open(ROOT / "logs" / "runs" / rec["run_log"], encoding="utf-8"))
llm = [e for e in log["turns"] if e.get("type") == "turn" and not e.get("forced")]
if sel == "first":
    e = llm[0]
elif sel.isdigit():
    e = next(x for x in llm if x["turn"] == int(sel))
else:
    e = next(x for x in llm if sel.lower() in (x.get("corrected_from_label") or x["action"]).lower())
think = e.get("llm_thinking") or ""
resp = e.get("llm_response") or ""
out = ROOT / "scratch" / "_cot" / f"{label}_r{run}_t{e['turn']}.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(f"log: {rec['run_log']}\nsuccess: {rec['success']} final_hp: {rec['final_hp']}\nturn: {e['turn']}\n"
               f"action: {e['action']}\ncorrected_from: {e.get('corrected_from_label')}\nhero: {e.get('hero')}\n"
               f"thinking chars: {len(think)}  response chars: {len(resp)}\n\n=== THINKING ===\n{think}\n\n=== RESPONSE ===\n{resp}\n",
               encoding="utf-8")
print(f"{label} r{run} T{e['turn']} {e['action']!r} from={e.get('corrected_from_label')!r} think={len(think)} resp={len(resp)} -> {out.name} ({rec['run_log']})")
