from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles

from agent.config import get_settings
from agent.tools import close_genai_client
from web.auth import (
    assert_auth_config,
    request_is_authenticated,
)
from web.agent_client import build_agent_client
from web.logging_config import configure_logging

# Import the routers at the top
from web.routers import auth, pages, summaries, infographics, jobs as jobs_router

# Import shared state/helpers from web.runtime
from web.runtime import (
    _is_auth_exempt_path,
    # Re-exported for test backward-compatibility
    AgentJob,  # noqa: F401
    jobs,  # noqa: F401
    infographics_cache,  # noqa: F401
    _display_error,  # noqa: F401
)

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    assert_auth_config()
    import web.runtime

    web.runtime.agent_client = build_agent_client()
    yield
    close_genai_client()
    web.runtime.agent_client = None


app = FastAPI(title="Infographics Agent Demo", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount(
    "/artifacts",
    StaticFiles(directory=Path(get_settings().artifact_dir)),
    name="artifacts",
)


@app.middleware("http")
async def require_password_auth(request: Request, call_next) -> Response:
    if _is_auth_exempt_path(request.url.path) or request_is_authenticated(request):
        return await call_next(request)

    if request.method == "GET":
        return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
    return PlainTextResponse(
        "Authentication required",
        status_code=401,
        headers={"HX-Redirect": "/login"},
    )


app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(summaries.router)
app.include_router(infographics.router)
app.include_router(jobs_router.router)
