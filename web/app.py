from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.config import get_settings
from agent.tools import close_genai_client
from web.auth import (
    assert_auth_config,
    request_is_authenticated,
)
from web.agent_client import build_agent_client
from web.logging_config import configure_logging

# Import routers
from web.routers import auth, pages, summaries, infographics, jobs
from web.runtime import _is_auth_exempt_path

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    assert_auth_config()
    app.state.agent_client = build_agent_client()
    yield
    close_genai_client()
    app.state.agent_client = None


def create_app() -> FastAPI:
    app = FastAPI(title="Infographics Agent Demo", lifespan=lifespan)

    # Initialize app state singletons/stores
    app.state.jobs = {}
    app.state.sessions = {}
    app.state.infographics_cache = {}
    app.state.background_tasks = set()
    app.state.templates = Jinja2Templates(directory=BASE_DIR / "templates")

    # Static file mounts
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.mount(
        "/artifacts",
        StaticFiles(directory=Path(get_settings().artifact_dir)),
        name="artifacts",
    )

    # Middleware
    @app.middleware("http")
    async def require_password_auth(request: Request, call_next) -> Response:
        if _is_auth_exempt_path(request.url.path) or request_is_authenticated(request):
            return await call_next(request)

        if request.method == "GET":
            return RedirectResponse(
                url=f"/login?next={request.url.path}", status_code=303
            )
        return PlainTextResponse(
            "Authentication required",
            status_code=401,
            headers={"HX-Redirect": "/login"},
        )

    # Include routers
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(summaries.router)
    app.include_router(infographics.router)
    app.include_router(jobs.router)

    return app
