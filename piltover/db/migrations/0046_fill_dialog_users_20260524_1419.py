from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from loguru import logger
from tortoise import migrations
from tortoise.expressions import Subquery
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps
from tortoise.models import MODEL
from tortoise.queryset import QuerySet, BulkUpdateQuery

if TYPE_CHECKING:
    from piltover.db.models import Dialog as DialogT, SavedDialog as SavedDialogT, ReadState as ReadStateT, \
        MessageDraft as MessageDraftT, Peer as PeerT

BATCH_SIZE = 1000


async def forwards_dialogs(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    from piltover.db.enums import PeerType

    Dialog: type[DialogT] = apps.get_model("models", "Dialog")

    await Dialog.filter(
        id__in=Subquery(Dialog.filter(owner_id__isnull=True, peer__owner_id__isnull=True).values("id"))
    ).delete()

    base_query = Dialog.filter(owner_id__isnull=True).order_by("id").limit(BATCH_SIZE).select_related("peer")
    total_count = await base_query.count()
    processed_count = 0

    offset_id = 0
    while dialogs := await base_query.filter(id__gt=offset_id):
        offset_id = dialogs[-1].id
        for dialog in dialogs:
            dialog.owner_id = dialog.peer.owner_id
            if dialog.peer.type is PeerType.CHANNEL:
                dialog.peer_id = dialog.peer.channel_peer_id

        if dialogs:
            await Dialog.bulk_update(dialogs, ["owner_id", "peer_id"])

        processed_count += len(dialogs)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) dialogs "
        )


async def forwards_saveddialogs(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    from piltover.db.enums import PeerType

    SavedDialog: type[SavedDialogT] = apps.get_model("models", "SavedDialog")

    await SavedDialog.filter(
        id__in=Subquery(SavedDialog.filter(owner_id__isnull=True, peer__owner_id__isnull=True).values("id"))
    ).delete()

    base_query = SavedDialog.filter(owner_id__isnull=True).order_by("id").limit(BATCH_SIZE).select_related("peer")
    total_count = await base_query.count()
    processed_count = 0

    offset_id = 0
    while dialogs := await base_query.filter(id__gt=offset_id):
        offset_id = dialogs[-1].id
        for dialog in dialogs:
            dialog.owner_id = dialog.peer.owner_id
            if dialog.peer.type is PeerType.CHANNEL:
                dialog.peer_id = dialog.peer.channel_peer_id

        if dialogs:
            await SavedDialog.bulk_update(dialogs, ["owner_id", "peer_id"])

        processed_count += len(dialogs)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) saved dialogs"
        )


async def forwards_readstates(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    from piltover.db.enums import PeerType

    ReadState: type[ReadStateT] = apps.get_model("models", "ReadState")

    await ReadState.filter(
        id__in=Subquery(ReadState.filter(owner_id__isnull=True, peer__owner_id__isnull=True).values("id"))
    ).delete()

    base_query = ReadState.filter(owner_id__isnull=True).order_by("id").limit(BATCH_SIZE).select_related("peer")
    total_count = await base_query.count()
    processed_count = 0

    offset_id = 0
    while states := await base_query.filter(id__gt=offset_id):
        offset_id = states[-1].id
        for state in states:
            state.owner_id = state.peer.owner_id
            if state.peer.type is PeerType.CHANNEL:
                state.peer_id = state.peer.channel_peer_id

        if states:
            await ReadState.bulk_update(states, ["owner_id", "peer_id"])

        processed_count += len(states)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) read states"
        )


async def forwards_messagedrafts(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    from piltover.db.enums import PeerType

    MessageDraft: type[MessageDraftT] = apps.get_model("models", "MessageDraft")

    await MessageDraft.filter(
        id__in=Subquery(MessageDraft.filter(user_id__isnull=True, peer__owner_id__isnull=True).values("id"))
    ).delete()

    base_query = MessageDraft.filter(user_id__isnull=True).order_by("id").limit(BATCH_SIZE).select_related("peer")
    total_count = await base_query.count()
    processed_count = 0

    offset_id = 0
    while drafts := await base_query.filter(id__gt=offset_id):
        offset_id = drafts[-1].id
        for draft in drafts:
            draft.user_id = draft.peer.owner_id
            if draft.peer.type is PeerType.CHANNEL:
                draft.peer_id = draft.peer.channel_peer_id

        if drafts:
            await MessageDraft.bulk_update(drafts, ["user_id", "peer_id"])

        processed_count += len(drafts)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) message drafts"
        )


async def backwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    ...


class Migration(migrations.Migration):
    dependencies = [('models', '0045_add_user_field_to_dialogs_readstate_draft_models_20260524_1413')]

    initial = False

    operations = [
        ops.RunPython(
            code=forwards_dialogs,
            reverse_code=backwards,
        ),
        ops.RunPython(
            code=forwards_saveddialogs,
            reverse_code=backwards,
        ),
        ops.RunPython(
            code=forwards_readstates,
            reverse_code=backwards,
        ),
        ops.RunPython(
            code=forwards_messagedrafts,
            reverse_code=backwards,
        ),
    ]
