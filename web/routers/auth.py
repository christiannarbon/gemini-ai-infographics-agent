from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from web.auth import (
    AUTH_COOKIE_NAME,
    auth_enabled,
    cookie_max_age,
    create_auth_cookie,
    password_matches,
)
from web.runtime import _safe_next_path
from web.dependencies import get_templates
from fastapi.templating import Jinja2Templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    next: str = "/",
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_path": _safe_next_path(next), "error": ""},
    )


@router.post("/login")
async def login(
    request: Request,
    password: str = Form(...),
    next_path: str = Form("/"),
    templates: Jinja2Templates = Depends(get_templates),
) -> Response:
    next_url = _safe_next_path(next_path)
    if not auth_enabled():
        return RedirectResponse(url=next_url, status_code=303)
    if not password_matches(password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next_path": next_url,
                "error": "Incorrect password.",
            },
            status_code=401,
        )

    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        create_auth_cookie(),
        max_age=cookie_max_age(),
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout() -> Response:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response
