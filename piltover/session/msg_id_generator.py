from time import time


class MsgIdGenerator:
    __slots__ = ("last_time", "offset",)

    def __init__(self, last_time: int = 0, offset: int = 0) -> None:
        self.last_time = last_time
        self.offset = offset

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def make_id(self, in_reply: bool) -> int:
        # Client message identifiers are divisible by 4, server message
        # identifiers modulo 4 yield 1 if the message is a response to
        # a client message, and 3 otherwise.

        now = int(time())
        self.offset = (self.offset + 4) if now == self.last_time else 0
        self.last_time = now
        msg_id = (now * 2 ** 32) + self.offset + (1 if in_reply else 3)

        # TODO: remove this check? msg_id%4 is always either 1 or 3
        if msg_id % 4 not in (1, 3):
            raise RuntimeError(f"Generated invalid server msg_id: {msg_id}")

        return msg_id
