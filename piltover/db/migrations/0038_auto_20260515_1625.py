from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0037_auto_20260510_1852')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='Channel',
            name='discussion',
            field=fields.OneToOneField('models.Channel', source_field='discussion_id', null=True, db_constraint=True, to_field='id', related_name='discussion_channel', on_delete=OnDelete.CASCADE),
        ),
    ]
