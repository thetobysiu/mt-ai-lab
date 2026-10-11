"""Record the guided tour of the platform as a captioned video (and one screenshot per step).

Heuristic runs and stored logs only: no API key, no model calls. Needs a running platform with the
thesis run logs downloaded (scripts/fetch_run_logs.py), Playwright with Microsoft Edge, and
imageio-ffmpeg for the mp4 conversion.

    python -m mota.dashboard                      # in another terminal
    python scripts/record_walkthrough.py [--url http://localhost:8080]
    -> docs/videos/walkthrough.mp4, docs/videos/walkthrough_voiceover.txt, docs/images/walkthrough/NN_<step>.png

Each caption carries its narration lines; the scene is held long enough to speak them, and the voice-over
script lists the lines with the video time at which each scene starts.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
W, H = 1600, 1000
WORDS_PER_S = 2.3  # a calm text-to-speech voice

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
        self.t0, self.cues = time.monotonic(), []

    def go(self, path: str, testid: str):
        self.page.goto(f"{self.base}{path}", wait_until="networkidle")
        self.page.wait_for_selector(f'[data-testid="{testid}"]', timeout=60_000)

    def say(self, step: str, title: str, text: str, voice: tuple[str, ...], block: bool = True) -> float:
        """Show a caption for as long as its narration takes; returns the deadline when block=False."""
        self.page.evaluate(_CAPTION_JS, [step, title, text])
        words = sum(len(line.split()) for line in voice)
        hold = words / WORDS_PER_S + 0.4 * len(voice) + 1.0
        self.cues.append((time.monotonic() - self.t0, step, title, voice))
        deadline = time.monotonic() + hold
        if block:
            self.until(deadline)
        return deadline

    def until(self, deadline: float):
        left = deadline - time.monotonic()
        if left > 0:
            self.page.wait_for_timeout(int(left * 1000))

    def shot(self, name: str):
        self.n += 1
        self.page.screenshot(path=str(self.shots / f"{self.n:02d}_{name}.png"))

    def wait(self, seconds: float):
        self.page.wait_for_timeout(int(seconds * 1000))


def tour(t: Tour):
    p = t.page

    # Intro and 1 Live
    t.go("/live/", "page-live")
    t.say("", "Magic Tower AI Lab",
          "A deterministic engine lists every legal action with its exact cost and what it unlocks; "
          "a language model picks one by number. This platform runs, watches and replays such agents.",
          ("Hello, and welcome to Magic Tower AI Lab.",
           "In the next few minutes, I'll show you around the platform.",
           "Magic Tower is a grid puzzle game.",
           "Every fight costs health, and the order of the fights decides whether the boss can be beaten at all.",
           "Here, a language model plays the game, but it never moves on the grid itself.",
           "A deterministic engine lists every legal action, with its exact cost and what it unlocks.",
           "The model simply picks one of them by number."))
    t.say("1 / 8 · Live", "Every run in one place",
          "Runs started here or from the command line appear live: label, floor, model, progress and result. "
          "Select a job to follow its map and decisions.",
          ("We start on the Live page.",
           "Every run appears here, whether you started it in the browser or from a terminal.",
           "You can see the label, the floor, the model, the progress, and the result.",
           "Select a job to follow its map and its decisions while it runs."))
    t.shot("live")

    # 2 Play with the heuristic
    t.go("/play/?floor=simple", "floor-map")
    end = t.say("2 / 8 · Play", "Run an agent on a floor",
                "Choose a floor, a model, a prompt and the planning mode. Here: the rule-based heuristic on the simple floor "
                "(no API key needed).",
                ("Next, the Play page.",
                 "At the top, you choose a floor, a model, a prompt, and the planning mode.",
                 "To keep things simple, we'll run the rule-based heuristic on the simple floor.",
                 "It needs no API key. Let's start it."), block=False)
    t.until(end - 2.0)
    p.get_by_test_id("btn-heuristic").click()
    p.wait_for_selector('[data-testid="score-outcome"]', state="attached", timeout=180_000)
    t.until(end)
    t.say("2 / 8 · Play", "Every decision is a turn card",
          "Each card shows the exact text the agent received, its answer and the executed action. "
          "The heuristic ends alive but never defeats the boss; the exact optimum would leave 13 HP.",
          ("Every decision becomes a turn card, on the right.",
           "A card shows the exact text the agent received, its answer, and the action that was executed.",
           "Cards marked forced are moves the engine makes on its own, like picking up keys.",
           "The heuristic survives, but it never defeats the boss.",
           "The best possible play would finish this floor with thirteen health points."))
    end = t.say("2 / 8 · Play", "Replay controls",
                "Scrub through the episode or use the arrow keys; fought monsters and collected items disappear from the map.",
                ("You can scrub through the whole episode with the slider, or with the arrow keys.",
                 "Watch the map: defeated monsters and collected items disappear as the episode goes on."), block=False)
    scrub = p.locator('[data-testid="scrubber"]')
    if scrub.count():
        top = int(scrub.get_attribute("max") or 0)
        for v in (0, top // 4, top // 2, (3 * top) // 4, top):
            scrub.fill(str(v))
            t.wait(1.2)
    t.until(end)
    t.shot("play_heuristic")

    # 3 Manual mode
    t.go("/play/?floor=simple", "floor-map")
    p.get_by_test_id("btn-manual").click()
    p.wait_for_selector('[data-testid="manual-action"]', timeout=60_000)
    end = t.say("3 / 8 · Manual mode", "Play it yourself",
                "Every legal action is ringed and numbered on the map, with the annotations the model receives. "
                "Click a tile to take it.",
                ("Now, let's play it ourselves.",
                 "Manual mode shows exactly the numbered actions the model receives.",
                 "Every legal action is ringed on the map, with its exact cost in health.",
                 "Below the map is the full prompt text, with all of the engine's annotations.",
                 "Click a tile to take that action.",
                 "This is the quickest way to see what the model is told, and what it has to work out by itself."),
                block=False)
    t.until(end - 9.0)
    for _ in range(3):
        cell = p.locator('[data-testid="floor-map"] [data-actionable="true"]').first
        if cell.count():
            cell.click()
            t.wait(2.0)
    t.until(end)
    t.shot("manual_mode")
    stop = p.get_by_role("button", name="End manual")
    if stop.count():
        stop.click()

    # 4 Maps
    t.go("/maps/", "page-maps")
    p.wait_for_selector('[data-testid="floor-map"] [data-x]', timeout=60_000)
    t.say("4 / 8 · Maps", "Every floor with its exact-solver facts",
          "Single floors show the exact optimum and the number of winning sets; the hand-designed floors have exactly one.",
          ("The Maps page lists every floor, together with the facts from the exact solver.",
           "For each single floor, you see the best possible result, and how many sets of fights can win it.",
           "The hand-designed floors have exactly one."))
    p.get_by_test_id("maps-tab-tower").click()
    p.locator('[data-testid="floor-item"][data-floor="MT5"]').click()
    p.wait_for_function("() => document.querySelector('[data-testid=\"page-maps\"]').innerText.includes('Map · MT5')", timeout=60_000)
    p.select_option('[data-testid="map-skin"]', "game")
    p.wait_for_selector('[data-testid="floor-map"][data-skin="game"]', timeout=20_000)
    t.say("4 / 8 · Maps", "The 24-floor tower",
          "Drawn with the original game's tiles; numbers are monster HP. The panel lists the floor's scripted events "
          "and whether the engine models them.",
          ("The tower tab shows all twenty-four floors of the original game, drawn with its own tiles.",
           "The numbers on the monsters are their health.",
           "The side panel lists each floor's scripted events, and whether the engine models them."))
    t.shot("maps_tower")
    p.select_option('[data-testid="map-skin"]', "classic")

    # 5 Thesis results and an episode replay
    t.go("/experiments/", "thesis-row")
    t.say("5 / 8 · Experiments → Thesis results", "The thesis, table by table",
          "Each table, figure and paragraph of Chapter 6 with the result files behind it: successes k/N with the "
          "Wilson interval, HP relative to the optimum, deaths.",
          ("Now, to the results of the thesis.",
           "Under Experiments, the Thesis results tab lists every table and figure of chapter six, with the result files behind it.",
           "For each file, you see the successes out of all episodes with a confidence interval, "
           "the health left relative to the optimum, and the number of deaths."))
    p.fill('[data-testid="thesis-filter"]', "Table 6.2")
    t.wait(1.0)
    p.locator('[data-testid="thesis-item"]', has_text="hand01_qwen3.5-397b_canon").first.click()
    p.wait_for_selector('[data-testid="thesis-episode"]', timeout=30_000)
    t.say("5 / 8 · Experiments → Thesis results", "Every episode can be replayed",
          "Qwen3.5-397B on the hand-designed floor hand01: five episodes, each with its run log.",
          ("Here is Qwen 3.5, with 397 billion parameters, on the hand-designed floor hand zero one.",
           "Five episodes, and each one comes with its full run log.",
           "Let's replay one of the wins."))
    t.shot("thesis_results")
    win = (p.locator('[data-testid="thesis-episode"]').filter(has=p.locator("td", has_text=re.compile(r"^win$")))
           .first.locator("a", has_text="replay"))
    win.click()
    p.wait_for_selector('[data-testid="log-replay"]', timeout=60_000)
    p.wait_for_function("() => document.querySelectorAll('[data-testid=\"floor-map\"] [data-x]').length > 0", timeout=60_000)
    end = t.say("5 / 8 · Replay", "What the model saw and thought",
                "The stored episode replays on the map; each turn card holds the observation, the model's reasoning and its choice.",
                ("The stored episode now replays on the map, turn by turn.",
                 "Each turn card holds what the model saw, how it reasoned, and what it chose.",
                 "So every decision in the thesis can be read exactly as the model saw it."), block=False)
    scrub = p.locator('[data-testid="scrubber"]')
    if scrub.count():
        top = int(scrub.get_attribute("max") or 0)
        for v in (top // 3, (2 * top) // 3, top):
            scrub.fill(str(v))
            t.wait(1.5)
    t.until(end)
    t.shot("episode_replay")

    # 6 Logs
    t.go("/logs/", "log-row")
    t.say("6 / 8 · Logs", "All stored episodes",
          "Every run log with its outcome, HP and model; the default shows the thesis episodes. "
          "Filter by scenario, floor and mode, or tick two logs to compare them at their first diverging turn.",
          ("The Logs page holds every stored episode, close to two thousand of them.",
           "Each row shows the outcome, the model, the final health, and the file name.",
           "You can filter by scenario, floor, and mode, or tick two runs to compare them from the turn where they first diverge."))
    p.select_option('[data-testid="log-scope-filter"]', "floor")
    t.wait(1.0)
    wins = p.locator('label', has_text="wins only").locator("input")
    if wins.count():
        wins.first.check()
        t.wait(1.5)
    t.say("6 / 8 · Logs", "Find the episodes you need",
          "Here: single floors, wins only. The play button opens any episode full-size, as in the replay before.",
          ("Here, we keep only single floors, and only the wins.",
           "The play button opens any episode full-size, just like the replay we saw before."))
    t.shot("logs")

    # 7 Re-run thesis experiments
    t.go("/experiments/", "page-experiments")
    p.get_by_test_id("tab-catalog").click()
    p.wait_for_selector('[data-testid="catalog-entry"]', timeout=30_000)
    t.say("7 / 8 · Re-run thesis experiments", "Reproduce with your own API key",
          "Select catalogue entries, optionally cap the episodes, and start them. The key stays in server memory only; "
          "results get a new label next to the thesis result.",
          ("If you want to reproduce an experiment, open the re-run catalogue.",
           "Paste your own API key, select the entries you want, optionally cap the number of episodes, and start them.",
           "Your key stays in the server's memory only, and is never written to disk.",
           "Each re-run gets its own label, right next to the thesis result."))
    t.shot("rerun_catalog")

    # 8 GEPA
    t.go("/gepa/", "gepa-run-row")
    p.locator('[data-testid="gepa-run-row"]', has_text="gs_dsv4flash_full").first.click()
    p.wait_for_selector('[data-testid="gepa-iterations"]', timeout=30_000)
    opener = p.locator('[data-testid="gepa-iter-open"]')
    if opener.count() > 1:
        opener.nth(1).click()
    t.say("8 / 8 · GEPA", "Prompt optimisation, iteration by iteration",
          "The teacher's diagnosis, the prompt diff against its parent, the validator's verdict and the score on each training floor.",
          ("Finally, the GEPA page.",
           "It shows prompt optimisation, one iteration at a time.",
           "You see the teacher model's diagnosis of the episodes, and the rewritten prompt, compared with its parent.",
           "Then the validator's verdict, and the score on every training floor."))
    t.shot("gepa")

    t.say("", "Next steps",
          "Read docs/walkthrough.md and docs/running-experiments.md · github.com/thetobysiu/mt-ai-lab",
          ("And that's the tour.",
           "Everything you've seen works without an API key.",
           "The full walkthrough, and the guide to running experiments, are in the docs folder of the repository.",
           "Thanks for watching!"))


def write_voiceover(cues: list, total: float, path: Path):
    def ts(s: float) -> str:
        return f"{int(s // 60)}:{int(s % 60):02d}"

    words = sum(len(line.split()) for *_, voice in cues for line in voice)
    out = ["MAGIC TOWER AI LAB - WALKTHROUGH VOICE-OVER",
           f"Video: walkthrough.mp4, {ts(total)}. One block per scene; the time range is where the scene sits in the video.",
           f"{words} words, written for about {round(WORDS_PER_S * 60)} words per minute. "
           "Each scene lasts a little longer than its lines, so start every block at its time.",
           ""]
    starts = [c[0] for c in cues] + [total]
    for i, (start, step, title, voice) in enumerate(cues):
        head = f"{step} - {title}" if step else ("Intro" if i == 0 else "Outro") + f" - {title}"
        out.append(f"=== Scene {i + 1}  [{ts(start)} - {ts(starts[i + 1])}]  {head}")
        out.extend(voice)
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


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
        t = Tour(page, a.url.rstrip("/"), a.shots)
        try:
            tour(t)
        finally:
            total = time.monotonic() - t.t0
            webm = Path(page.video.path())
            ctx.close()
            browser.close()
        import imageio_ffmpeg
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(webm), "-t", f"{total + 1:.1f}",
               "-c:v", "libx264",
               "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.out)]
        if subprocess.run(cmd).returncode != 0:
            shutil.copy(webm, a.out.with_suffix(".webm"))
            raise SystemExit("ffmpeg failed; the raw recording is next to the target as .webm")
    voice = a.out.with_name(a.out.stem + "_voiceover.txt")
    write_voiceover(t.cues, total, voice)
    print(f"video -> {a.out} ({a.out.stat().st_size / 2**20:.1f} MB); voice-over -> {voice}; screenshots -> {a.shots}")


if __name__ == "__main__":
    main()
