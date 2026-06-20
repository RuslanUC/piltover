from loguru import logger
from orjson import loads
from tortoise import fields
from tortoise import migrations
from tortoise.fields.data import JSON_DUMPS
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps

BATCH_SIZE = 1000


async def forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    MessageContent = apps.get_model("models", "MessageContent")

    base_query = MessageContent.filter().order_by("id").limit(BATCH_SIZE).prefetch_related("messagerelateds")
    total_count = await MessageContent.all().count()
    processed_count = 0

    offset_id = 0
    while contents := await base_query.filter(id__gt=offset_id):
        offset_id = contents[-1].id
        to_update = []
        for content in contents:
            if not content.messagerelateds:
                continue
            user_ids = []
            chat_ids = []
            channel_ids = []
            for rel in content.messagerelateds:
                if rel.user_id is not None:
                    user_ids.append(rel.user_id)
                elif rel.chat_id is not None:
                    chat_ids.append(rel.chat_id)
                elif rel.channel_id is not None:
                    channel_ids.append(rel.channel_id)
            content.related_users = user_ids or None
            content.related_chats = chat_ids or None
            content.related_channels = channel_ids or None
            to_update.append(content)

        if to_update:
            await MessageContent.bulk_update(to_update, ["related_users", "related_chats", "related_channels"])

        processed_count += len(contents)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) messages"
        )


class Migration(migrations.Migration):
    dependencies = [('models', '0056_auto_20260617_1910')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='related_channels',
            field=fields.JSONField(null=True, encoder=JSON_DUMPS, decoder=loads),
        ),
        ops.AddField(
            model_name='MessageContent',
            name='related_chats',
            field=fields.JSONField(null=True, encoder=JSON_DUMPS, decoder=loads),
        ),
        ops.AddField(
            model_name='MessageContent',
            name='related_users',
            field=fields.JSONField(null=True, encoder=JSON_DUMPS, decoder=loads),
        ),
        ops.RunPython(
            code=forwards,
        ),
        ops.DeleteModel(name='MessageRelated'),
    ]
