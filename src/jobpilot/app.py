"""jobPilot — FastAPI web app.

Runs a local server in a daemon thread and opens the user's browser.
All app state is set up in the lifespan context and attached to app.state.
"""

import asyncio
import logging
import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import pystray
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw

from jobpilot.config import Config
from jobpilot.db import Database
from jobpilot.ladder import compute_ladder
from jobpilot.pipeline import run_pipeline
from jobpilot.scrapers.adzuna import AdzunaScraper
from jobpilot.state import ProfileStore, SearchParamsStore

logger = logging.getLogger(__name__)

PORT = 8765
RESOURCES_DIR = Path(__file__).parent / "resources"
TEMPLATES_DIR = RESOURCES_DIR / "templates" / "html"
STATIC_DIR = RESOURCES_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = Config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Propagate scraper credentials to os.environ for scrapers that read from it
    if config.adzuna_app_id:
        os.environ["ADZUNA_APP_ID"] = config.adzuna_app_id
    if config.adzuna_app_key:
        os.environ["ADZUNA_APP_KEY"] = config.adzuna_app_key
    if config.jooble_api_key:
        os.environ["JOOBLE_API_KEY"] = config.jooble_api_key

    db = Database(config.db_path)

    app.state.config = config
    app.state.db = db
    app.state.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    app.state.profile_store = ProfileStore(config.data_dir)
    app.state.search_params_store = SearchParamsStore(config.data_dir)
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.run_status = {}  # run_id -> {"stage": str, "result": dict|None, "error": str|None}
    app.state.background_tasks = set()

    recent = db.get_recent_runs(limit=1)
    if (
        recent
        and recent[0].get("completed_at") is not None
        and app.state.profile_store.has_profile()
        and app.state.search_params_store.has_params()
    ):
        last_completed = datetime.fromisoformat(recent[0]["completed_at"])
        if last_completed.tzinfo is None:
            last_completed = last_completed.replace(tzinfo=timezone.utc)
        if (
            datetime.now(timezone.utc) - last_completed > timedelta(hours=12)
            and compute_ladder(config, db)["state"] != "gift_exhausted"
        ):
            _profile = app.state.profile_store.load()
            _sp = app.state.search_params_store.load()
            _client = app.state.client
            _run_id = db.start_run()
            app.state.run_status[_run_id] = {
                "stage": "starting",
                "result": None,
                "error": None,
            }
            _scrapers = [AdzunaScraper(_sp)]

            def _make_update_stage(rid):
                def _update_stage(stage: str) -> None:
                    app.state.run_status[rid]["stage"] = stage

                return _update_stage

            async def _auto_run(
                _rid=_run_id,
                _prof=_profile,
                _search_params=_sp,
                _scr=_scrapers,
                _c=_client,
            ):
                try:
                    result = await asyncio.to_thread(
                        run_pipeline,
                        db,
                        _prof,
                        _search_params,
                        config,
                        _scr,
                        _c,
                        _rid,
                        _make_update_stage(_rid),
                    )
                    app.state.run_status[_rid]["stage"] = "done"
                    app.state.run_status[_rid]["result"] = result
                except Exception as exc:
                    logger.error(f"Auto-refresh run {_rid} failed: {exc}")
                    app.state.run_status[_rid]["stage"] = "error"
                    app.state.run_status[_rid]["error"] = str(exc)

            task = asyncio.create_task(_auto_run())
            app.state.background_tasks.add(task)
            task.add_done_callback(app.state.background_tasks.discard)

    yield

    db.close()


def create_app() -> FastAPI:
    from jobpilot.routes.api import router as api_router
    from jobpilot.routes.matches import router as matches_router
    from jobpilot.routes.search_params import router as search_params_router
    from jobpilot.routes.settings import router as settings_router
    from jobpilot.routes.wizard import router as wizard_router

    app = FastAPI(title="jobPilot", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(wizard_router)
    app.include_router(matches_router)
    app.include_router(settings_router)
    app.include_router(search_params_router)
    app.include_router(api_router)
    return app


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _serve(app: FastAPI) -> None:
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def _build_tray_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill="#0d6efd")
    return img


def main() -> None:
    if _port_in_use(PORT):
        webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return

    fastapi_app = create_app()
    threading.Thread(target=_serve, args=(fastapi_app,), daemon=True).start()
    time.sleep(0.8)
    webbrowser.open(f"http://127.0.0.1:{PORT}/")

    def _open(_icon, _item):
        webbrowser.open(f"http://127.0.0.1:{PORT}/")

    def _quit(icon, _item):
        icon.stop()

    tray = pystray.Icon(
        "jobPilot",
        _build_tray_image(),
        "jobPilot",
        menu=pystray.Menu(
            pystray.MenuItem("Open jobPilot", _open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _quit),
        ),
    )
    tray.run()
