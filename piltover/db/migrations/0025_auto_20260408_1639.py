from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0024_auto_20260408_1505')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Update',
            name='encrypted_chat',
            field=fields.ForeignKeyField('models.EncryptedChat', source_field='encrypted_chat_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
