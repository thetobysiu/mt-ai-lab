"""Record the guided tour of the platform as a captioned video (and one screenshot per step).

Heuristic runs and stored logs only: no API key, no model calls. Needs a running platform with the
thesis run logs downloaded (scripts/fetch_run_logs.py), Playwright with Microsoft Edge, and
imageio-ffmpeg for the mp4 conversion.

    python -m mota.dashboard                      # in another terminal
    python scripts/record_walkthrough.py [--url http://localhost:8080]
    -> docs/videos/walkthrough.mp4, docs/images/walkthrough/NN_<step>.png
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
W, H = 1600, 1000

_CAPTION_JS = """([step, title, text]) => {
  let box = document.getElementById('wt-caption');
  if (!box) {
    box = document.createElement('div');
    box.id = 'wt-caption';
    box.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99999;max-width:1180px;'
      + 'background:rgba(10,14,24,.92);color:#f3f4f6;border:1px solid rgba(255,255,255,.18);border-radius:12px;'
      + 'padding:14px 22px;font:18px/1.45 system-ui,Segoe UI,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.45);pointer-events:none';
    document.body.appendChild(box);
  }
  box.innerHTML = (step ? `<div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#93c5fd;margin-bottom:4px">${step}</div>` : '')
    + `<div style="font-weight:600;font-size:20px;margin-bottom:2px">${title}</div><div>${text}</div>`;
}"""


class Tour:
    def __init__(self, page: Page, base: str, shots: Path):
        self.page, self.base, self.shots, self.n = page, base, shots, 0

    def go(self, path: str, testid: str):
        self.page.goto(f"{self.base}{path}", wait_until="networkidle")
        self.page.wait_for_selector(f'[data-testid="{testid}"]', timeout=60_000)

    def say(self, step: str, title: str, text: str, hold: float = 5.0):
        self.page.evaluate(_CAPTION_JS, [step, title, text])
        self.page.wait_for_timeout(int(hold * 1000))

    def shot(self, name: str):
        self.n += 1
        self.page.screenshot(path=str(self.shots / f"{self.n:02d}_{name}.png"))

    def wait(self, seconds: float):
        self.page.wait_for_timeout(int(seconds * 1000))


def tour(t: Tour):
    p = t.page

    # 1 Live
    t.go("/live/", "page-live")
    t.say("", "Magic Tower AI Lab",
          "A deterministic engine lists every legal action with its exact cost and what it unlocks; "
          "a language model picks one by number. This platform runs, watches and replays such agents.", 7)
    t.say("1 / 8 · Live", "Every run in one place",
          "Runs started here or from the command line appear live: label, floor, model, progress and result. "
          "Select a job to follow its map and decisions.", 6)
    t.shot("live")

    # 2 Play with the heuristic
    t.go("/play/?floor=simple", "floor-map")
    t.say("2 / 8 · Play", "Run an agent on a floor",
          "Choose a floor, a model, a prompt and the planning mode. Here: the rule-based heuristic on the simple floor "
          "(no API key needed).", 6)
    p.get_by_test_id("btn-heuristic").click()
    p.wait_for_selector('[data-testid="score-outcome"]', state="attached", timeout=180_000)
    t.say("2 / 8 · Play", "Every decision is a turn card",
          "Each card shows the exact text the agent received, its answer and the executed action. "
          "The heuristic ends alive but never defeats the boss; the exact optimum would leave 13 HP.", 7)
    scrub = p.locator('[data-testid="scrubber"]')
    if scrub.count():
        top = int(scrub.get_attribute("max") or 0)
        for v in (0, top // 4, top // 2, (3 * top) // 4, top):
            scrub.fill(str(v))
            t.wait(1.2)
    t.say("2 / 8 · Play", "Replay controls",
          "Scrub through the episode or use the arrow keys; fought monsters and collected items disappear from the map.", 4)
    t.shot("play_heuristic")

    # 3 Manual mode
    t.go("/play/?floor=simple", "floor-map")
    p.get_by_test_id("btn-manual").click()
    p.wait_for_selector('[data-testid="manual-action"]', timeout=60_000)
    t.say("3 / 8 · Manual mode", "Play it yourself",
          "Every legal action is ringed and numbered on the map, with the annotations the model receives. "
          "Click a tile to take it.", 6)
    for _ in range(3):
        cell = p.locator('[data-testid="floor-map"] [data-actionable="true"]').first
        if cell.count():
            cell.click()
            t.wait(2.0)
    t.shot("manual_mode")
    end = p.get_by_role("button", name="End manual")
    if end.count():
        end.click()

    # 4 Maps
    t.go("/maps/", "page-maps")
    p.wait_for_selector('[data-testid="floor-map"] [data-x]', timeout=60_000)
    t.say("4 / 8 · Maps", "Every floor with its exact-solver facts",
          "Single floors show the exact optimum and the number of winning sets; the hand-designed floors have exactly one.", 5)
    p.get_by_test_id("maps-tab-tower").click()
    p.locator('[data-testid="floor-item"][data-floor="MT5"]').click()
    p.wait_for_function("() => document.querySelector('[data-testid=\"page-maps\"]').innerText.includes('Map · MT5')", timeout=60_000)
    p.select_option('[data-testid="map-skin"]', "game")
    p.wait_for_selector('[data-testid="floor-map"][data-skin="game"]', timeout=20_000)
    t.say("4 / 8 · Maps", "The 24-floor tower",
          "Drawn with the original game's tiles; numbers are monster HP. The panel lists the floor's scripted events "
          "and whether the engine models them.", 6)
    t.shot("maps_tower")
    p.select_option('[data-testid="map-skin"]', "classic")

    # 5 Thesis results and an episode replay
    t.go("/experiments/", "thesis-row")
    t.say("5 / 8 · Experiments → Thesis results", "The thesis, table by table",
          "Each table, figure and paragraph of Chapter 6 with the result files behind it: successes k/N with the "
          "Wilson interval, HP relative to the optimum, deaths.", 7)
    p.fill('[data-testid="thesis-filter"]', "Table 6.2")
    t.wait(1.0)
    p.locator('[data-testid="thesis-item"]', has_text="hand01_qwen3.5-397b_canon").first.click()
    p.wait_for_selector('[data-testid="thesis-episode"]', timeout=30_000)
    t.say("5 / 8 · Experiments → Thesis results", "Every episode can be replayed",
          "Qwen3.5-397B on the hand-designed floor hand01: five episodes, each with its run log.", 5)
    t.shot("thesis_results")
    win = (p.locator('[data-testid="thesis-episode"]').filter(has=p.locator("td", has_text=re.compile(r"^win$")))
           .first.locator("a", has_text="replay"))
    win.click()
    p.wait_for_selector('[data-testid="log-replay"]', timeout=60_000)
    p.wait_for_function("() => document.querySelectorAll('[data-testid=\"floor-map\"] [data-x]').length > 0", timeout=60_000)
    t.say("5 / 8 · Replay", "What the model saw and thought",
          "The stored episode replays on the map; each turn card holds the observation, the model's reasoning and its choice.", 6)
    scrub = p.locator('[data-testid="scrubber"]')
    if scrub.count():
        top = int(scrub.get_attribute("max") or 0)
        for v in (top // 3, (2 * top) // 3, top):
            scrub.fill(str(v))
            t.wait(1.5)
    t.shot("episode_replay")

    # 6 Logs
    t.go("/logs/", "log-row")
    t.say("6 / 8 · Logs", "All stored episodes",
          "Every run log with its outcome, HP and model; the default shows the thesis episodes. "
          "Filter by scenario, floor and mode, or tick two logs to compare them at their first diverging turn.", 6)
    p.select_option('[data-testid="log-scope-filter"]', "floor")
    t.wait(1.0)
    wins = p.locator('label', has_text="wins only").locator("input")
    if wins.count():
        wins.first.check()
        t.wait(1.5)
    t.say("6 / 8 · Logs", "Find the episodes you need",
          "Here: single floors, wins only. The play button opens any episode full-size, as in the replay before.", 5)
    t.shot("logs")

    # 7 Re-run thesis experiments
    t.go("/experiments/", "page-experiments")
    p.get_by_test_id("tab-catalog").click()
    p.wait_for_selector('[data-testid="catalog-entry"]', timeout=30_000)
    t.say("7 / 8 · Re-run thesis experiments", "Reproduce with your own API key",
          "Select catalogue entries, optionally cap the episodes, and start them. The key stays in server memory only; "
          "results get a new label next to the thesis result.", 7)
    t.shot("rerun_catalog")

    # 8 GEPA
    t.go("/gepa/", "gepa-run-row")
    p.locator('[data-testid="gepa-run-row"]', has_text="gs_dsv4flash_full").first.click()
    p.wait_for_selector('[data-testid="gepa-iterations"]', timeout=30_000)
    opener = p.locator('[data-testid="gepa-iter-open"]')
    if opener.count() > 1:
        opener.nth(1).click()
    t.say("8 / 8 · GEPA", "Prompt optimisation, iteration by iteration",
          "The teacher's diagnosis, the prompt diff against its parent, the validator's verdict and the score on each training floor.", 7)
    t.shot("gepa")

    t.say("", "Next steps",
          "Read docs/walkthrough.md and docs/running-experiments.md · github.com/thetobysiu/mt-ai-lab", 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--channel", default="msedge")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "videos" / "walkthrough.mp4")
    ap.add_argument("--shots", type=Path, default=ROOT / "docs" / "images" / "walkthrough")
    a = ap.parse_args()
    a.shots.mkdir(parents=True, exist_ok=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
        browser = pw.chromium.launch(channel=a.channel)
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=tmp,
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        try:
            tour(Tour(page, a.url.rstrip("/"), a.shots))
        finally:
            webm = Path(page.video.path())
            ctx.close()
            browser.close()
        import imageio_ffmpeg
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264",
               "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.out)]
        if subprocess.run(cmd).returncode != 0:
            shutil.copy(webm, a.out.with_suffix(".webm"))
            raise SystemExit("ffmpeg failed; the raw recording is next to the target as .webm")
    print(f"video -> {a.out} ({a.out.stat().st_size / 2**20:.1f} MB); screenshots -> {a.shots}")


if __name__ == "__main__":
    main()
