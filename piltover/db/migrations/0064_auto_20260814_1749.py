from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0063_auto_20260802_1504')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ProtectedUsername',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('username', fields.CharField(unique=True, max_length=64)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('channel', fields.ForeignKeyField('models.Channel', source_field='channel_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('removed_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'protectedusername', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
