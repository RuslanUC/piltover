from abc import ABC


class WriteHook(ABC):
    __slots__ = ("condition",)

    def __init__(self, condition: str) -> None:
        self.condition = condition


# class WriteHookCallConverter(WriteHook):
#     __slots__ = ("converter_func",)
#
#     def __init__(self, condition: str, converter_func: str) -> None:
#         super().__init__(condition)
#         self.converter_func = converter_func


class WriteHookRunCode(WriteHook):
    __slots__ = ("code",)

    def __init__(self, condition: str, code: list[str]) -> None:
        super().__init__(condition)
        self.code = code


WRITE_HOOKS: dict[str, list[WriteHook]] = {
    "messages.InvitedUsers": [
        WriteHookRunCode(
            condition="ctx.layer < 177",
            code=["return self.updates.write(ctx)"],
        ),
    ],
}
