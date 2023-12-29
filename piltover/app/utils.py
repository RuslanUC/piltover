from functools import wraps
from inspect import signature
from typing import Callable

from piltover.db.models import User, UserAuthorization
from piltover.exceptions import ErrorRpc


def auth_required(func: Callable):
    @wraps(func)
    async def auth_check(client, *args, **kwargs):
        auth = await UserAuthorization.get_or_none(key__id=str(client.auth_data.auth_key_id)).select_related("user")
        if auth is None:
            raise ErrorRpc(error_code=401, error_message="ACTIVE_USER_REQUIRED")  # ??

        if "user" in signature(func).parameters:
            kwargs["user"] = auth.user

        return await func(client, *args, **kwargs)

    return auth_check
