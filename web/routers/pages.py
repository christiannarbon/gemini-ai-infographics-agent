from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from web.auth import auth_enabled
from web.main import templates

router = APIRouter()


@router.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "ok"


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"auth_enabled": auth_enabled()},
    )
