"""Consistent error responses: {"detail": {"code": ..., "message": ...}}."""

from typing import Any

from fastapi import HTTPException


class AppError(HTTPException):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(status_code=status, detail={"code": code, "message": message, **extra})


def not_found(what: str) -> AppError:
    return AppError(404, "not_found", f"{what} was not found.")


def conflict(code: str, message: str, **extra: Any) -> AppError:
    return AppError(409, code, message, **extra)


def invalid(code: str, message: str) -> AppError:
    return AppError(422, code, message)
