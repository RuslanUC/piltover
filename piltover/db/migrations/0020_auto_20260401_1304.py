from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0019_auto_20260331_1409')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Update',
            name='peer',
            field=fields.ForeignKeyField('models.Peer', source_field='peer_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
