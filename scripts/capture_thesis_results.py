"""Screenshot of Experiments -> Thesis results with Table 6.2 expanded (docs/images/fig_thesis_results.png)."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
out = Path(__file__).resolve().parents[1] / "docs" / "images" / "fig_thesis_results.png"
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto(f"{base}/experiments/", wait_until="networkidle")
    page.wait_for_selector('[data-testid="thesis-row"]')
    page.locator('[data-testid="thesis-item"]', has_text="hand01_qwen3.5-397b_canon").first.click()
    page.wait_for_selector('[data-testid="thesis-episode"]')
    page.wait_for_timeout(500)
    page.screenshot(path=str(out))
    browser.close()
print("saved", out)
