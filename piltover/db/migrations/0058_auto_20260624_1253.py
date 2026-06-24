from loguru import logger
from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps

BATCH_SIZE = 1000


async def update_users_last_seen(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    User = apps.get_model("models", "User")
    Presence = apps.get_model("models", "Presence")

    base_query = Presence.all().order_by("id").select_related("user").only("id", "last_seen", "user_id", "user__id")
    total_count = await base_query.count()
    processed_count = 0

    offset_id = 0
    while presences := await base_query.limit(BATCH_SIZE).filter(id__gt=offset_id):
        offset_id = presences[-1].id
        to_update = []
        for presence in presences:
            presence.user.last_seen = presence.last_seen
            to_update.append(presence.user)

        if to_update:
            await User.bulk_update(to_update, ["last_seen"])

        processed_count += len(presences)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) users"
        )


class Migration(migrations.Migration):
    dependencies = [('models', '0057_auto_20260624_1216')]

    initial = False

    operations = [
        ops.AddField(
            model_name='User',
            name='last_seen',
            field=fields.DatetimeField(auto_now=False, auto_now_add=True),
        ),
        ops.RunPython(
            code=update_users_last_seen,
        ),
        ops.RunSQL(
            sql="UPDATE user SET last_seen='2000-01-01' WHERE last_seen<'2000-01-01';"
        ),
        ops.DeleteModel(name='Presence'),
    ]
