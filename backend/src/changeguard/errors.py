"""Error hierarchy shared by every module.

Each error carries a stable machine-readable ``code`` and an HTTP ``status`` so
the API layer can translate it into an RFC 9457 problem response without
leaking internals. Messages must be safe to show to end users: they never
contain stack traces, absolute server paths, or uploaded file contents.
"""

from __future__ import annotations


class ChangeGuardError(Exception):
    code = "changeguard_error"
    status = 400
    title = "Request could not be processed"

    def __init__(self, message: str, *, detail: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class InputError(ChangeGuardError):
    code = "invalid_input"
    status = 422
    title = "Invalid input"


class PatchParseError(InputError):
    code = "malformed_patch"
    title = "Malformed patch"

    def __init__(self, message: str, *, line_number: int | None = None) -> None:
        detail: dict[str, object] = {}
        if line_number is not None:
            detail["line"] = line_number
            message = f"{message} (patch line {line_number})"
        super().__init__(message, detail=detail)
        self.line_number = line_number


class PayloadTooLargeError(InputError):
    code = "payload_too_large"
    status = 413
    title = "Payload too large"


class UnsupportedInputError(InputError):
    code = "unsupported_input"
    status = 415
    title = "Unsupported input"


class ArchiveError(InputError):
    code = "invalid_archive"
    title = "Invalid repository archive"


class CoverageParseError(InputError):
    code = "invalid_coverage_report"
    title = "Invalid coverage report"


class PatchApplyError(ChangeGuardError):
    """A hunk could not be applied to the provided base snapshot.

    This is recoverable: the pipeline falls back to diff-only analysis for the
    affected file and records a warning.
    """

    code = "patch_apply_failed"
    title = "Patch does not apply to the repository snapshot"


class NotFoundError(ChangeGuardError):
    code = "not_found"
    status = 404
    title = "Not found"


class RateLimitedError(ChangeGuardError):
    code = "rate_limited"
    status = 429
    title = "Too many requests"


class AuthenticationError(ChangeGuardError):
    code = "unauthorized"
    status = 401
    title = "Authentication required"
