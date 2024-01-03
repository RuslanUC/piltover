from dataclasses import dataclass
from io import BytesIO
from typing import Generic, TypeVar

from piltover.tl_new import TLObject, SerializationUtils

T = TypeVar("T")


@dataclass(init=True, repr=True, frozen=True)
class EncryptedMessage:
    auth_key_id: int
    msg_key: bytes
    encrypted_data: bytes


@dataclass(init=True, repr=True, frozen=True)
class DecryptedMessage:
    salt: bytes
    session_id: int
    message_id: int
    seq_no: int
    message_data: bytes
    padding: bytes

    def to_core_message(self):
        return CoreMessage(
            message_id=self.message_id,
            seq_no=self.seq_no,
            obj=SerializationUtils.read(BytesIO(self.message_data), TLObject),
        )


@dataclass(init=True, repr=True, frozen=True)
class UnencryptedMessage:
    message_id: int
    message_data: bytes


@dataclass(init=True, repr=True, frozen=True, kw_only=True)
class CoreMessage(Generic[T]):
    message_id: int
    seq_no: int
    obj: T
