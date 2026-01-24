from __future__ import annotations

from contextvars import ContextVar
from os import environ
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piltover.gateway import Gateway


USE_REAL_TCP_FOR_TESTING = environ.get("USE_REAL_TCP_FOR_TESTING", "").lower() in ("true", "1")

server_instance: ContextVar[Gateway] = ContextVar("server_instance")
test_phone_number: ContextVar[str] = ContextVar("test_phone_number")
skipping_auth: ContextVar[bool] = ContextVar("skipping_auth")
