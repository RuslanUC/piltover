from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import SecretUpdateType
from piltover.tl import Long
from piltover.tl.types import UpdateNewEncryptedMessage, UpdateEncryptedMessagesRead, EncryptedMessage, \
    EncryptedMessageService, EncryptedFileEmpty

UpdateTypes = UpdateNewEncryptedMessage | UpdateEncryptedMessagesRead


class SecretUpdate(Model):
    id: int = fields.BigIntField(pk=True)
    qts: int = fields.BigIntField()
    type: SecretUpdateType = fields.IntEnumField(SecretUpdateType)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    authorization: models.UserAuthorization = fields.ForeignKeyField("models.UserAuthorization")
    chat: models.EncryptedChat = fields.ForeignKeyField("models.EncryptedChat")
    data: bytes = fields.BinaryField(null=True, default=None)

    message_random_id: int | None = fields.BigIntField(null=True, default=None)
    message_is_service: bool | None = fields.BooleanField(null=True, default=None)

    authorization_id: int
    chat_id: int

    async def to_tl(self) -> UpdateTypes | None:
        match self.type:
            case SecretUpdateType.NEW_MESSAGE:
                if self.message_is_service:
                    message = EncryptedMessageService(
                        random_id=self.message_random_id,
                        chat_id=self.chat_id,
                        date=int(self.date.timestamp()),
                        bytes_=self.data,
                    )
                else:
                    message = EncryptedMessage(
                        random_id=self.message_random_id,
                        chat_id=self.chat_id,
                        date=int(self.date.timestamp()),
                        bytes_=self.data,
                        file=EncryptedFileEmpty(), # TODO: files support
                    )

                return UpdateNewEncryptedMessage(
                    message=message,
                    qts=self.qts,
                )

            case SecretUpdateType.MESSAGE_READ:
                return UpdateEncryptedMessagesRead(
                    chat_id=self.chat_id,
                    max_date=Long.read_bytes(self.data),
                    date=int(self.date.timestamp()),
                )

        return None
