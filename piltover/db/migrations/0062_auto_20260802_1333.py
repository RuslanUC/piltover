from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0061_auto_20260731_1737')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Stickerset',
            name='managed_by_bot',
            field=fields.ForeignKeyField('models.User', source_field='managed_by_bot_id', null=True, db_constraint=True, to_field='id', related_name='managed_sets', on_delete=OnDelete.CASCADE),
        ),
    ]
