from tortoise import migrations
from tortoise.migrations import operations as ops
from piltover.db.models.utils import PartialIndexNonNull
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0053_auto_20260529_1452')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageRef',
            name='scheduled_by_user',
            field=fields.ForeignKeyField('models.User', source_field='scheduled_by_user_id', null=True, db_constraint=True, to_field='id', related_name='message_scheduled', on_delete=OnDelete.CASCADE),
        ),
        ops.AddIndex(
            model_name='MessageRef',
            index=PartialIndexNonNull(fields=['peer_id', 'scheduled_by_user_id']),
        ),
    ]
