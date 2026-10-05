"""Repository paths in one place.

The 24-floor game data lives in ``data/games/24/project``; set ``MOTA_GAME_ROOT`` to a folder that contains
``24/project`` (and optionally ``51/project``) to use another copy.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GAME_ROOT = Path(os.environ.get("MOTA_GAME_ROOT") or REPO_ROOT / "data" / "games")
GAME_24 = GAME_ROOT / "24" / "project"
FLOORS_24 = GAME_24 / "floors"
DATA_JS_24 = GAME_24 / "data.js"
SINGLE_FLOORS = REPO_ROOT / "data" / "floors"
JAVA_BFS = REPO_ROOT / "tools" / "java_bfs"
RESULTS = REPO_ROOT / "results"
LOGS = Path(os.environ.get("MOTA_LOGS_DIR") or REPO_ROOT / "logs")
RUN_LOGS = LOGS / "runs"
