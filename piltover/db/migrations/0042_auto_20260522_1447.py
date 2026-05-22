from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0041_auto_20260522_1414')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Peer',
            name='channel_peer',
            field=fields.ForeignKeyField('models.Peer', source_field='channel_peer_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
