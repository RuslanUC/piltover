from loguru import logger
from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps

BATCH_SIZE = 1000


async def update_users_pts(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    User = apps.get_model("models", "User")
    State = apps.get_model("models", "State")

    base_query = State.all().order_by("id").select_related("user")
    total_count = await base_query.count()
    processed_count = 0

    offset_id = 0
    while states := await base_query.limit(BATCH_SIZE).filter(id__gt=offset_id):
        offset_id = states[-1].id
        to_update = []
        for state in states:
            state.user.pts = state.pts
            to_update.append(state.user)

        if to_update:
            await User.bulk_update(to_update, ["pts"])

        processed_count += len(states)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) users"
        )


class Migration(migrations.Migration):
    dependencies = [('models', '0056_auto_20260617_1910')]

    initial = False

    operations = [
        ops.AddField(
            model_name='User',
            name='pts',
            field=fields.BigIntField(default=0),
        ),
        ops.RunPython(
            code=update_users_pts,
        ),
        ops.DeleteModel(name='State'),
    ]
