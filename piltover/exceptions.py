from typing import Any


class Error(Exception):
    pass


class Disconnection(Error):
    def __init__(self, error: int | None = None):
        if error is not None and error > 0:
            error *= -1
        self.transport_error = error


class ErrorRpc(Error):
    __slots__ = ("error_code", "error_message", "reason",)

    def __init__(self, error_code: int, error_message: str, reason: str | None = None):
        self.error_code = error_code
        self.error_message = error_message
        self.reason = reason

    @classmethod
    def check(cls, cond: Any, message: str, code: int = 400) -> None:
        if not cond:
            raise cls(code, message)


class InvalidConstructorException(Error):
    def __init__(self, constructor: int | bytes, wrong_type: bool = False, leftover_bytes: bytes = b""):
        self.constructor = constructor
        self.wrong_type = wrong_type
        self.leftover_bytes = leftover_bytes


class Unreachable(RuntimeError):
    def __init__(self, message: str = "Unreachable") -> None:
        super().__init__(message)
