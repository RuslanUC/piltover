from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import DialogFilter


class DialogFolder(Model):
    id: int = fields.BigIntField(pk=True)
    id_for_user: int = fields.SmallIntField()
    name: str = fields.CharField(max_length=16)
    owner: models.User = fields.ForeignKeyField("models.User")
    position: int = fields.SmallIntField(default=0)
    contacts: bool = fields.BooleanField(default=False)
    non_contacts: bool = fields.BooleanField(default=False)
    groups: bool = fields.BooleanField(default=False)
    broadcasts: bool = fields.BooleanField(default=False)
    bots: bool = fields.BooleanField(default=False)
    exclude_muted: bool = fields.BooleanField(default=False)
    exclude_read: bool = fields.BooleanField(default=False)
    exclude_archived: bool = fields.BooleanField(default=False)

    # dialogs: fields.ManyToManyRelation[models.Dialog] = fields.ManyToManyField("models.Dialog")

    async def to_tl(self) -> DialogFilter:
        return DialogFilter(
            id=self.id,
            title=self.name,
            contacts=self.contacts,
            non_contacts=self.non_contacts,
            groups=self.groups,
            broadcasts=self.broadcasts,
            bots=self.bots,
            exclude_muted=self.exclude_muted,
            exclude_read=self.exclude_read,
            exclude_archived=self.exclude_archived,
            pinned_peers=[],  # TODO: add dialog filter pinned peers
            include_peers=[],  # TODO: add included peers
            exclude_peers=[],  # TODO: add excluded peers
        )

    def get_difference(self, tl_filter: DialogFilter) -> list[str]:
        updated_fields = []
        for slot in tl_filter.__slots__:
            if not hasattr(self, slot):
                continue
            if getattr(self, slot) != getattr(tl_filter, slot):
                updated_fields.append(slot)

        if self.name != tl_filter.title:
            updated_fields.append("name")

        return updated_fields

    def fill_from_tl(self, tl_filter: DialogFilter) -> None:
        self.name = tl_filter.title
        self.contacts = tl_filter.contacts
        self.non_contacts = tl_filter.non_contacts
        self.groups = tl_filter.groups
        self.broadcasts = tl_filter.broadcasts
        self.bots = tl_filter.bots
        self.exclude_muted = tl_filter.exclude_muted
        self.exclude_read = tl_filter.exclude_read
        self.exclude_archived = tl_filter.exclude_archived
