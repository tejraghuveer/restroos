from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

PROBLEM_JSON = "application/problem+json"


@dataclass(slots=True)
class ProblemDetail:
    type: str
    title: str
    status: int
    detail: str
    code: str
    instance: str | None = None
    errors: list[dict] | None = None

    def as_dict(self) -> dict:
        body = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }
        if self.instance:
            body["instance"] = self.instance
        if self.errors:
            body["errors"] = self.errors
        return body


class AppError(Exception):
    """Domain error that maps to an RFC 7807 response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        title: str | None = None,
        type_: str = "about:blank",
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.title = title or "Bad Request"
        self.type = type_


class Unauthorized(AppError):
    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, "unauthorized", detail)


class Forbidden(AppError):
    def __init__(self, detail: str = "You do not have access to this resource") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, "forbidden", detail)


class NotFound(AppError):
    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "not_found", detail)


class Conflict(AppError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, code, detail)


class ValidationFailed(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(422, "validation_error", detail)


def unauthorized_exception(detail: str = "Authentication required") -> HTTPException:
    """For OpenAPI security declarations where a dependency raises HTTPException."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
