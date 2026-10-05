"""Filesystem roots shared by every dashboard router (env-overridable for tests)."""
from __future__ import annotations

import os
from pathlib import Path

from ...paths import DATA_JS_24 as DATA_JS, FLOORS_24 as FLOORS_DIR, GAME_ROOT, JAVA_BFS, REPO_ROOT, SINGLE_FLOORS

HERE = Path(__file__).resolve().parents[1]          # mota/dashboard/
GEPA_ROOT = REPO_ROOT                               # repository root
PROJECT_ROOT = GAME_ROOT                            # folder that contains 24/project (and optionally 51/project)
LOGS_DIR = Path(os.environ.get("MOTA_LOGS_DIR") or GEPA_ROOT / "logs")
RESULTS_DIR = Path(os.environ.get("MOTA_RESULTS_DIR") or GEPA_ROOT / "results")
JOBS_DIR = LOGS_DIR / "jobs"
WEB_OUT = HERE / "web" / "out"
LEGACY_DIR = HERE / "legacy"
