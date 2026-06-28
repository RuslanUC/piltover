from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0056_auto_20260617_1910')]

    initial = False

    operations = [
        ops.CreateModel(
            name='TelegramUser',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('user', fields.OneToOneField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('telegram_id', fields.BigIntField(db_index=True)),
            ],
            options={'table': 'telegramuser', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
