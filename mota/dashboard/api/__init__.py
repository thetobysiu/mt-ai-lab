"""Dashboard API routers."""
from . import (floors, prompts, models, evaluate, manual, bfs, gepa_runs, logs, reliability, latency, projects,
               settings, catalog, thesis)

ROUTERS = [floors.router, prompts.router, models.router, evaluate.router, manual.router, bfs.router,
           gepa_runs.router, logs.router, reliability.router, latency.router, projects.router,
           settings.router, catalog.router, thesis.router]
