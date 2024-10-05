from asyncio import iscoroutinefunction
from typing import Iterable

from piltover.db.models import User
from piltover.tl import TLObject


class ToTL:
    def __init__(self, cls: type[TLObject], compile_args_: Iterable[str], **kwargs) -> None:
        self.cls = cls
        self.compile_args = compile_args_
        self.kwargs = kwargs

    async def to_tl(self, user: User) -> TLObject:
        new_kwargs = {}

        for arg in self.compile_args:
            arg = arg.split(".")
            arg_name = arg[0]
            path = arg[1:]
            value = self.kwargs[arg_name]
            for name in path:
                value = getattr(value, name)

            if iscoroutinefunction(value):
                func = value
            elif hasattr(value, "to_tl"):
                func = value.to_tl
            else:
                continue

            new_kwargs[arg_name] = await func(user)

        return self.cls(**(self.kwargs | new_kwargs))
