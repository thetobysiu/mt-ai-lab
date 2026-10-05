"""
Browser smoke test of the Next.js dashboard (heuristic only — no LLM calls).

Requires a running dashboard with a built front end. Opens every page, runs a heuristic episode
on simple and a tower segment MT0->MT2 through the UI, checks the two-tier footer, the deep link
and the Live view.

    python scripts/smoke_dashboard.py [--url http://localhost:8080] [--channel msedge]
"""
from __future__ import annotations

import argparse
import sys
import time

from playwright.sync_api import sync_playwright

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PASSED = FAILED = 0


def check(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label} {extra}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--channel", default="msedge")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        print("\n--- pages ---")
        for path, tid in [("/live/", "page-live"), ("/play/", "page-play"), ("/maps/", "page-maps"), ("/experiments/", "page-experiments"),
                          ("/gepa/", "page-gepa"), ("/logs/", "page-logs"), ("/reference/", "page-reference"),
                          ("/projects/", "page-projects")]:
            page.goto(f"{base}{path}", wait_until="networkidle")
            check(f"{path} renders", page.locator(f'[data-testid="{tid}"]').count() == 1)

        print("\n--- maps browser: single floors and tower in separate tabs ---")
        page.goto(f"{base}/maps/", wait_until="networkidle")
        page.wait_for_selector('[data-testid="floor-map"] [data-x]', timeout=30_000)
        singles = page.locator('[data-testid="floor-item"]').count()
        check("single-floor tab lists reference + hand + generated floors", singles >= 21, str(singles))
        check("single-floor tab has no tower floors", page.locator('[data-testid="floor-item"][data-floor="MT5"]').count() == 0)
        page.locator('[data-testid="floor-item"][data-floor="hand03"]').click()
        page.wait_for_function("() => document.querySelector('[data-testid=\"page-maps\"]').innerText.includes('Map · hand03')", timeout=30_000)
        check("hand03 shows its exact-solver facts", page.get_by_test_id("floor-facts").inner_text().count("9") >= 1)
        page.get_by_test_id("maps-tab-tower").click()
        page.locator('[data-testid="floor-item"][data-floor="MT5"]').click()
        page.wait_for_function("() => document.querySelector('[data-testid=\"page-maps\"]').innerText.includes('Map · MT5')", timeout=30_000)
        time.sleep(0.5)
        check("MT5 map renders 13x13", page.locator('[data-testid="floor-map"] [data-x]').count() == 169)
        check("MT5 scripted events shown (openShop modelled)", page.locator('[data-testid="page-maps"] .tag-ok', has_text="openShop").count() >= 1)
        check("play link points at the floor", (page.get_by_test_id("maps-play").get_attribute("href") or "").endswith("floor=MT5"))
        page.select_option('[data-testid="map-skin"]', "game")
        page.wait_for_selector('[data-testid="floor-map"][data-skin="game"]', timeout=10_000)
        textured = page.locator('[data-testid="floor-map"] [data-x][style*="/sprites/"]').count()
        check("game-texture view draws every MT5 tile from the original sprites", textured == 169, str(textured))
        page.select_option('[data-testid="map-skin"]', "classic")

        print("\n--- experiments catalog, GEPA runs, planning control ---")
        page.goto(f"{base}/experiments/", wait_until="networkidle")
        page.wait_for_selector('[data-testid="thesis-row"]', timeout=30_000)
        check("thesis results follow Table F.4", page.locator('[data-testid="thesis-row"]').count() >= 30)
        page.locator('[data-testid="thesis-item"]').first.click()
        page.wait_for_selector('[data-testid="thesis-episode"]', timeout=30_000)
        check("a thesis result file lists its episodes", page.locator('[data-testid="thesis-episode"]').count() >= 1)
        page.get_by_test_id("tab-catalog").click()
        page.wait_for_selector('[data-testid="catalog-entry"]', timeout=30_000)
        check("catalog lists the thesis experiments", page.locator('[data-testid="catalog-entry"]').count() >= 15)
        check("catalog shows the thesis result of G1", "10/10" in page.locator('[data-testid="catalog-entry"][data-id="final-stack"]').inner_text())
        check("API key panel never shows a key", page.get_by_test_id("api-key-input").first.get_attribute("type") == "password")
        page.goto(f"{base}/gepa/", wait_until="networkidle")
        page.wait_for_selector('[data-testid="gepa-run-row"]', timeout=30_000)
        page.locator('[data-testid="gepa-run-row"]', has_text="gs_dsv4flash_full").click()
        page.wait_for_selector('[data-testid="gepa-iterations"]', timeout=30_000)
        page.locator('[data-testid="gepa-iter-open"]').nth(1).click()
        check("iteration details show a prompt diff", page.get_by_test_id("prompt-diff").count() == 1)
        check("study card attached to the run", page.get_by_test_id("gepa-study-card").count() == 1)
        page.goto(f"{base}/play/", wait_until="networkidle")
        page.get_by_test_id("btn-setup").click() if page.get_by_test_id("planning-select").count() == 0 else None
        check("planning selector offers the six thesis conditions", page.locator('[data-testid="planning-select"] option').count() == 6)
        check("no Chunk-N control any more", page.locator('[data-testid="chunk-size"]').count() == 0)

        print("\n--- deep link + heuristic episode on simple ---")
        page.goto(f"{base}/?floor=simple", wait_until="networkidle")
        page.wait_for_url("**/play/?floor=simple", timeout=10_000)
        check("/?floor=simple redirects to /play", "/play/" in page.url)
        page.wait_for_selector('[data-testid="floor-map"]')
        check("preview map has 11x11 cells", page.locator('[data-testid="floor-map"] [data-x]').count() == 121)
        page.get_by_test_id("btn-heuristic").click()
        page.wait_for_selector('[data-testid="score-outcome"]', state="attached", timeout=120_000)
        time.sleep(1.0)
        check("outcome shown first (FAILED for heuristic simple)", page.get_by_test_id("score-outcome").inner_text() == "FAILED")
        check("legacy composite 0.3712", page.get_by_test_id("score-total").inner_text() == "0.3712")
        check("36 turn cards", page.locator('[data-testid="card-turn"]').count() == 36)
        check("run log saved", page.locator('[data-testid="log-saved"]').count() == 1)

        print("\n--- tower MT0->MT2 ---")
        page.goto(f"{base}/play/?floor=mota24", wait_until="networkidle")
        page.wait_for_function("() => document.querySelectorAll('[data-testid=\"end-floor\"] option').length > 1")
        page.select_option('[data-testid="end-floor"]', "MT2")
        page.get_by_test_id("btn-heuristic").click()
        page.wait_for_selector('[data-testid="score-outcome"]', state="attached", timeout=180_000)
        time.sleep(1.0)
        check("tower GOAL", page.get_by_test_id("score-outcome").inner_text() == "GOAL")
        check("floor_change cards", page.locator('[data-testid="card-floor_change"]').count() >= 2)
        check("tower scenario badge + floor progress", page.get_by_test_id("scenario-badge").inner_text().startswith("tower")
              and page.get_by_test_id("floor-progress").count() == 1)
        check("tower shows the shop economy (gold/EXP)", page.locator('[data-testid="stat-gold-exp"]').count() == 1)
        sw = page.locator('[data-testid="floor-switcher"] select')
        check("tower map has a floor switcher", sw.count() == 1 and sw.locator("option").count() >= 2)
        sw.select_option("MT0")
        time.sleep(0.4)
        check("switching floor shows that floor without the hero", page.locator('[data-testid="floor-map"] [data-x]').count() > 0
              and page.locator('[data-testid="floor-map"]').inner_text().count("@") == 0)
        # all-floors view: every visited floor at the current step, hero on exactly one card
        page.get_by_test_id("btn-all-floors").click()
        time.sleep(0.5)
        cards = page.locator('[data-testid="floor-card"]')
        check("all-floors view shows one card per visited floor", cards.count() >= 3, str(cards.count()))
        check("all-floors view marks the hero floor once", page.locator('[data-testid="floor-card"].is-hero').count() == 1)
        check("all-floors cards are drawn (cells present)", page.locator('[data-testid="floor-card"] [data-x]').count() > 100)
        # scrub to turn 0: only the first floor has been entered, later ones are dimmed
        page.locator('[data-testid="scrubber"]').fill("0")
        time.sleep(0.4)
        check("at turn 0 later floors are marked not yet visited", page.locator('[data-testid="floor-card"].is-unvisited').count() >= 2)
        cards.first.click()
        time.sleep(0.3)
        check("clicking a card opens it full size", page.locator('[data-testid="all-floors"]').count() == 0
              and page.locator('[data-testid="floor-map"]').count() == 1)

        print("\n--- manual mode (click the map) ---")
        page.goto(f"{base}/play/?floor=simple", wait_until="networkidle")
        page.get_by_test_id("btn-manual").click()
        page.wait_for_selector('[data-testid="manual-action"]', timeout=30_000)
        n0 = page.locator('[data-testid="manual-action"]').count()
        page.locator('[data-testid="manual-action"]').first.click()
        time.sleep(1.0)
        check("manual action applied (turn card appears)", page.locator('[data-testid="card-turn"]').count() >= 1 and n0 > 0)
        cell = page.locator('[data-testid="floor-map"] [data-actionable="true"]').first
        check("legal actions are highlighted on the map", cell.count() == 1)
        cell.click()
        time.sleep(1.0)
        check("clicking a highlighted tile takes the action", page.locator('[data-testid="card-turn"]').count() >= 2)
        page.get_by_role("button", name="End manual").click()

        print("\n--- live view ---")
        page.goto(f"{base}/live/", wait_until="networkidle")
        page.wait_for_selector('[data-testid="job-row"]', timeout=30_000)
        check("jobs table lists the UI runs", page.locator('[data-testid="job-row"][data-status="done"]').count() >= 2)
        check("jobs table shows steps per call", page.locator('[data-testid="job-plan"]').count() > 0)
        page.get_by_test_id("job-sort-label").click()
        asc = page.locator('[data-testid="job-row"] td:nth-child(3)').all_inner_texts()
        page.get_by_test_id("job-sort-label").click()
        desc = page.locator('[data-testid="job-row"] td:nth-child(3)').all_inner_texts()
        check("click on a column sorts the jobs (asc, then desc)",
              page.get_by_test_id("job-sort-label").get_attribute("aria-sort") == "descending" and asc == desc[::-1])
        page.get_by_test_id("job-sort-label").click()  # third click: back to newest first
        n_jobs = page.locator('[data-testid="job-row"]').count()
        page.fill('[data-testid="job-filter"]', "heuristic")
        time.sleep(0.3)
        check("job filter narrows the list", 0 < page.locator('[data-testid="job-row"]').count() <= n_jobs)
        page.fill('[data-testid="job-filter"]', "")
        page.wait_for_function("() => document.querySelector('[data-testid=\"stat-event-stream\"]').textContent.includes('open')", timeout=10_000)
        check("websocket open (KPI tile)", True)
        check("KPI row present", page.locator('[data-testid^="stat-"]').count() >= 5)
        page.locator('[data-testid="job-row"]').first.click()
        page.wait_for_selector('[data-testid="selected-job"]')
        time.sleep(2.0)
        check("selected job replays its map", page.locator('[data-testid="floor-map"] [data-x]').count() > 0)
        check("open in Play link", page.get_by_test_id("sel-open-play").count() == 1)

        print("\n--- experiments + logs ---")
        page.goto(f"{base}/experiments/", wait_until="networkidle")
        page.get_by_test_id("tab-results").click()
        page.wait_for_selector('[data-testid="result-row"]', timeout=30_000)
        check("results table populated", page.locator('[data-testid="result-row"]').count() > 0)
        n_thesis = page.locator('[data-testid="result-row"]').count()
        page.select_option('[data-testid="results-scope"]', "all")
        time.sleep(0.4)
        check("results scope 'all' shows at least the thesis results", page.locator('[data-testid="result-row"]').count() >= n_thesis)
        page.goto(f"{base}/logs/", wait_until="networkidle")
        page.wait_for_selector('[data-testid="log-row"]', timeout=60_000)
        page.select_option('[data-testid="log-source-filter"]', "all")  # the smoke runs above are not thesis episodes
        page.uncheck('[data-testid="log-hide-incomplete"]')
        time.sleep(0.4)
        n_all = page.locator('[data-testid="log-row"]').count()
        page.select_option('[data-testid="log-scope-filter"]', "tower")
        time.sleep(0.4)
        tower_rows = page.locator('[data-testid="log-row"]').count()
        only_tower = page.locator('[data-testid="log-row"][data-scenario="tower"]').count()
        check("scenario filter: tower only", tower_rows > 0 and tower_rows == only_tower, f"{tower_rows}/{only_tower}")
        page.select_option('[data-testid="log-scope-filter"]', "floor")
        time.sleep(0.4)
        floor_rows = page.locator('[data-testid="log-row"]').count()
        check("scenario filter: single floors only", floor_rows > 0 and floor_rows + tower_rows == n_all,
              f"{floor_rows}+{tower_rows} vs {n_all}")
        page.select_option('[data-testid="log-floor-filter"]', "simple")
        time.sleep(0.4)
        check("floor filter narrows the list", 0 < page.locator('[data-testid="log-row"]').count() <= floor_rows)
        check("boss outcome is tagged", page.locator('[data-testid="log-row"]', has_text="boss ").count() > 0)
        check("each row shows its filename", page.locator('[data-testid="log-row-file"]').first.inner_text().endswith(".json"))
        check("each row links to Play", page.locator('[data-testid="log-row-play"]').first.get_attribute("href").startswith("/play/?log="))
        page.locator('[data-testid="log-row"]').first.click()
        page.wait_for_selector('[data-testid="log-download"]', timeout=60_000)
        check("log detail shows filename + download", page.get_by_test_id("log-filename").inner_text().startswith("logs/runs/"))
        check("replay has a progress bar next to the map", page.locator('[data-testid="scrubber"]').count() == 1
              and page.locator('[data-testid="btn-replay"]').count() == 1)
        page.select_option('[data-testid="log-mode-filter"]', "heuristic")  # a run with real fights (created above)
        time.sleep(0.5)
        page.wait_for_selector('[data-testid="log-row-play"]', timeout=30_000)
        target = page.locator('[data-testid="log-row-play"]').first.get_attribute("href")
        page.goto(f"{base}{target}", wait_until="networkidle")
        page.wait_for_selector('[data-testid="log-replay"]', timeout=30_000)
        page.wait_for_function("() => document.querySelectorAll('[data-testid=\"floor-map\"] [data-x]').length > 0", timeout=60_000)
        check("row → Play replays the stored run", page.locator('[data-testid="card-turn"]').count() > 0)
        # killed monsters must stay gone while scrubbing (producers differ: cumulative vs per-turn `removed`)
        enemies = '[data-testid="floor-map"] [data-t="E"]:not(.opacity-40)'
        scrub = page.locator('[data-testid="scrubber"]')
        n_steps = int(scrub.get_attribute("max") or 0)
        scrub.fill("0"); time.sleep(0.3)
        e0 = page.locator(enemies).count()
        scrub.fill(str(n_steps)); time.sleep(0.4)
        e1 = page.locator(enemies).count()
        check("fought monsters disappear during replay", n_steps > 0 and e1 < e0, f"{e0} → {e1}")
        check("scenario is labelled on the map", page.get_by_test_id("scenario-badge").inner_text() in ("single floor", "tower"))

        print("\n--- layout: no horizontal overflow, map is the biggest element ---")
        for w, h in [(1280, 800), (1920, 1080), (2560, 1400)]:
            page.set_viewport_size({"width": w, "height": h})
            page.goto(f"{base}/play/?floor=simple", wait_until="networkidle")
            page.wait_for_selector('[data-testid="floor-map"]')
            time.sleep(0.5)
            m = page.evaluate("""() => {
              const de = document.documentElement, r = document.querySelector('[data-testid="floor-map"]').getBoundingClientRect();
              return {ox: de.scrollWidth - innerWidth, area: Math.round(r.width * r.height), side: Math.round(r.width)};
            }""")
            check(f"{w}px: no horizontal overflow", m["ox"] <= 1, str(m["ox"]))
            check(f"{w}px: map scales with the viewport", m["side"] >= (300 if w < 1900 else 600), str(m["side"]))
        page.set_viewport_size({"width": 1500, "height": 950})

        page.goto(f"{base}/live/", wait_until="networkidle")
        page.get_by_test_id("rail-toggle").click()
        time.sleep(0.3)
        wide = page.evaluate("() => document.querySelector('main').getBoundingClientRect().width")
        check("collapsed sidebar: work area keeps the page width", wide > 1200, str(round(wide)))
        page.get_by_test_id("rail-toggle").click()

        check("no uncaught page errors", not errors, "; ".join(errors)[:300])
        browser.close()
    print(f"\nResults: {PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
