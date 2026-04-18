from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0026_auto_20260412_1538')]

    initial = False

    operations = [
        ops.AddField(
            model_name='UserReactionsSettings',
            name='default_custom_emoji',
            field=fields.ForeignKeyField('models.File', source_field='default_custom_emoji_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
