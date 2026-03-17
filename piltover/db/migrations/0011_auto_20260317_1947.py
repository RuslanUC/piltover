from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0010_auto_20260316_1614')]

    initial = False

    operations = [
        ops.CreateModel(
            name='UserEmojiStatus',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('user', fields.OneToOneField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('emoji', fields.ForeignKeyField('models.File', source_field='emoji_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('until', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'useremojistatus', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
