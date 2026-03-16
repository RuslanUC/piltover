from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0009_auto_20260315_2023')]

    initial = False

    operations = [
        ops.CreateModel(
            name='MessageUniqueView',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('message', fields.ForeignKeyField('models.MessageContent', source_field='message_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'messageuniqueview', 'app': 'models', 'unique_together': (('message', 'user'),), 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
