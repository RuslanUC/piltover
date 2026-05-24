from tortoise import migrations
from tortoise.expressions import F
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps


async def peer_to_peer2_dialog_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    Dialog = apps.get_model("models", "Dialog")
    await Dialog.all().update(peer2_id=F("peer_id"))


async def peer2_to_peer_dialog_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    Dialog = apps.get_model("models", "Dialog")
    await Dialog.all().update(peer_id=F("peer2_id"))


async def peer_to_peer2_draft_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    MessageDraft = apps.get_model("models", "MessageDraft")
    await MessageDraft.all().update(peer2_id=F("peer_id"))


async def peer2_to_peer_draft_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    MessageDraft = apps.get_model("models", "MessageDraft")
    await MessageDraft.all().update(peer_id=F("peer2_id"))


async def peer_to_peer2_readstate_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    ReadState = apps.get_model("models", "ReadState")
    await ReadState.all().update(peer2_id=F("peer_id"))


async def peer2_to_peer_readstate_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    ReadState = apps.get_model("models", "ReadState")
    await ReadState.all().update(peer_id=F("peer2_id"))


async def peer_to_peer2_saveddialog_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    SavedDialog = apps.get_model("models", "SavedDialog")
    await SavedDialog.all().update(peer2_id=F("peer_id"))


async def peer2_to_peer_saveddialog_forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    SavedDialog = apps.get_model("models", "SavedDialog")
    await SavedDialog.all().update(peer_id=F("peer2_id"))


async def backwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    raise NotImplementedError


class Migration(migrations.Migration):
    dependencies = [('models', '0043_fill_channel_peers_20260522_1459')]

    initial = False
    atomic = False

    operations = [
        ops.AddField(
            model_name='Dialog',
            name='peer2',
            field=fields.ForeignKeyField('models.Peer', source_field='peer2_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE, related_name="dialog2"),
        ),
        ops.RunPython(
            code=peer_to_peer2_dialog_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='Dialog', name='peer'),
        ops.AddField(
            model_name='Dialog',
            name='peer',
            field=fields.ForeignKeyField('models.Peer', source_field='peer_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.RunPython(
            code=peer2_to_peer_dialog_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='Dialog', name='peer2'),

        ops.AddField(
            model_name='MessageDraft',
            name='peer2',
            field=fields.ForeignKeyField('models.Peer', source_field='peer2_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE, related_name="draft2"),
        ),
        ops.RunPython(
            code=peer_to_peer2_draft_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='MessageDraft', name='peer'),
        ops.AddField(
            model_name='MessageDraft',
            name='peer',
            field=fields.ForeignKeyField('models.Peer', source_field='peer_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.RunPython(
            code=peer2_to_peer_draft_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='MessageDraft', name='peer2'),

        ops.AddField(
            model_name='ReadState',
            name='peer2',
            field=fields.ForeignKeyField('models.Peer', source_field='peer2_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE, related_name="readstate2"),
        ),
        ops.RunPython(
            code=peer_to_peer2_readstate_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='ReadState', name='peer'),
        ops.AddField(
            model_name='ReadState',
            name='peer',
            field=fields.ForeignKeyField('models.Peer', source_field='peer_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.RunPython(
            code=peer2_to_peer_readstate_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='ReadState', name='peer2'),

        ops.AddField(
            model_name='SavedDialog',
            name='peer2',
            field=fields.ForeignKeyField('models.Peer', source_field='peer2_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE, related_name="saveddialog2"),
        ),
        ops.RunPython(
            code=peer_to_peer2_saveddialog_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='SavedDialog', name='peer'),
        ops.AddField(
            model_name='SavedDialog',
            name='peer',
            field=fields.ForeignKeyField('models.Peer', source_field='peer_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.RunPython(
            code=peer2_to_peer_saveddialog_forwards,
            reverse_code=backwards,
        ),
        ops.RemoveField(model_name='SavedDialog', name='peer2'),
    ]
