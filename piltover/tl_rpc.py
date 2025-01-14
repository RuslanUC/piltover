from piltover.tl import TLObject, Long, Int, objects

# TODO: remove whole file because these constructors are defined in tools/resources/internal.tl and wil lbe generated automatically

# internal.rpc_response = flags:# transport_error:flags.0?int obj:flags.1?Object = internal.RpcResponse
class RpcResponse(TLObject):
    __tl_id__ = 0x1c05a4e9
    __tl_name__ = "types.internal.CallRpc"

    __slots__ = ("transport_error", "obj",)

    def __init__(self, *, transport_error: int | None = None, obj: TLObject | None = None):
        self.transport_error = transport_error
        self.obj = obj

    def serialize(self) -> bytes:
        flags = 0
        if self.transport_error is not None:
            flags |= 1 << 0
        if self.obj is not None:
            flags |= 1 << 1

        result = Int.write(flags)
        if self.transport_error is not None:
            result += Int.write(self.transport_error)
        if self.obj is not None:
            result += self.obj.write()

        return result

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        flags = Int.read(stream)

        transport_error = Int.read(stream) if flags & (1 << 0) else None
        obj = TLObject.read(stream) if flags & (1 << 1) else None

        return cls(transport_error=transport_error, obj=obj)


# internal.call_rpc = flags:# key_is_temp:flags.0?true auth_key_id:flags.1?long session_id:flags.2?long message_id:flags.3?long auth_id:flags.4?long user_id:flags.5?long obj:Object = internal.RpcResponse
class CallRpc(TLObject):
    __tl_id__ = 0xa6961f84
    __tl_name__ = "types.internal.CallRpc"

    __slots__ = ("obj", "key_is_temp", "auth_key_id", "session_id", "message_id", "auth_id", "user_id",)

    def __init__(
            self, *, obj: TLObject, key_is_temp: bool = False, auth_key_id: int | None = None,
            session_id: int | None = None, message_id: int | None = None, auth_id: int | None = None,
            user_id: int | None = None,
    ):
        self.obj = obj
        self.key_is_temp = key_is_temp
        self.auth_key_id = auth_key_id
        self.session_id = session_id
        self.message_id = message_id
        self.auth_id = auth_id
        self.user_id = user_id

    def serialize(self) -> bytes:
        flags = 0

        if self.key_is_temp:
            flags |= 1 << 0
        if self.auth_key_id is not None:
            flags |= 1 << 1
        if self.session_id is not None:
            flags |= 1 << 2
        if self.message_id is not None:
            flags |= 1 << 3
        if self.auth_id is not None:
            flags |= 1 << 4
        if self.user_id is not None:
            flags |= 1 << 5

        result = Int.write(flags)

        if self.auth_key_id is not None:
            result += Long.write(self.auth_key_id)
        if self.session_id is not None:
            result += Long.write(self.session_id)
        if self.message_id is not None:
            result += Long.write(self.message_id)
        if self.auth_id is not None:
            result += Long.write(self.auth_id)
        if self.user_id is not None:
            result += Long.write(self.user_id)

        result += self.obj.write()

        return result

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        flags = Int.read(stream)

        key_is_temp = (flags & (1 << 0)) == (1 << 0)
        auth_key_id = Long.read(stream) if flags & (1 << 1) else None
        session_id = Long.read(stream) if flags & (1 << 2) else None
        message_id = Long.read(stream) if flags & (1 << 3) else None
        auth_id = Long.read(stream) if flags & (1 << 4) else None
        user_id = Long.read(stream) if flags & (1 << 5) else None

        obj = TLObject.read(stream)

        return cls(
            obj=obj,
            key_is_temp=key_is_temp,
            auth_key_id=auth_key_id,
            session_id=session_id,
            message_id=message_id,
            auth_id=auth_id,
            user_id=user_id,
        )


objects[RpcResponse.__tl_id__] = RpcResponse
objects[CallRpc.__tl_id__] = CallRpc
