from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0004_auto_20260303_1935')]

    initial = False

    operations = [
        ops.CreateModel(
            name='DefaultSendAs',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('group', fields.ForeignKeyField('models.Channel', source_field='group_id', db_constraint=True, to_field='id', related_name='default_send_as_group', on_delete=OnDelete.CASCADE)),
                ('channel', fields.ForeignKeyField('models.Channel', source_field='channel_id', db_constraint=True, to_field='id', related_name='default_send_as_channel', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'defaultsendas', 'app': 'models', 'unique_together': (('user_id', 'group_id'),), 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
