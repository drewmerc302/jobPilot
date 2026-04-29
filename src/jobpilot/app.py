"""jobPilot — FastAPI web app.

Runs a local server in a daemon thread and opens the user's browser.
All app state is set up in the lifespan context and attached to app.state.
"""

import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jobpilot.config import Config
from jobpilot.db import Database
from jobpilot.state import ProfileStore, SearchParamsStore

PORT = 8765
RESOURCES_DIR = Path(__file__).parent / "resources"
TEMPLATES_DIR = RESOURCES_DIR / "templates" / "html"
STATIC_DIR = RESOURCES_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = Config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Make Adzuna keys available to AdzunaScraper (reads from os.environ)
    if config.adzuna_app_id:
        os.environ["ADZUNA_APP_ID"] = config.adzuna_app_id
    if config.adzuna_app_key:
        os.environ["ADZUNA_APP_KEY"] = config.adzuna_app_key

    db = Database(config.db_path)

    app.state.config = config
    app.state.db = db
    app.state.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    app.state.profile_store = ProfileStore(config.data_dir)
    app.state.search_params_store = SearchParamsStore(config.data_dir)
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.run_status = {}  # run_id -> {"stage": str, "result": dict|None, "error": str|None}
    app.state.background_tasks = set()

    yield

    db.close()


def create_app() -> FastAPI:
    from jobpilot.routes.api import router as api_router
    from jobpilot.routes.matches import router as matches_router
    from jobpilot.routes.wizard import router as wizard_router

    app = FastAPI(title="jobPilot", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(wizard_router)
    app.include_router(matches_router)
    app.include_router(api_router)
    return app


def _serve(app: FastAPI) -> None:
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def main() -> None:
    app = create_app()
    threading.Thread(target=_serve, args=(app,), daemon=True).start()
    time.sleep(0.8)
    webbrowser.open(f"http://127.0.0.1:{PORT}/")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
