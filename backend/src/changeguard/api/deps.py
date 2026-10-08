"""FastAPI dependencies."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Depends, Header, Request

from changeguard.api.security import check_api_key, client_identity
from changeguard.api.state import AppState
from changeguard.errors import InputError

WORKSPACE_HEADER = "X-ChangeGuard-Workspace"
_WORKSPACE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.changeguard
    return state


def require_key(request: Request, state: Annotated[AppState, Depends(get_state)]) -> None:
    check_api_key(state.settings, request)


def rate_limited(request: Request, state: Annotated[AppState, Depends(get_state)]) -> None:
    state.limiter.check(client_identity(state.settings, request))


def get_workspace(
    workspace: Annotated[
        str | None,
        Header(
            alias=WORKSPACE_HEADER,
            description="Opaque workspace ID. Requests that carry one only see analyses created in it.",
        ),
    ] = None,
) -> str | None:
    """Scope for reads and writes; ``None`` (no header) is unscoped operator access."""
    if workspace is None:
        return None
    if not _WORKSPACE.fullmatch(workspace):
        raise InputError("invalid workspace ID: expected 16-64 letters, digits, '-' or '_'")
    return workspace
