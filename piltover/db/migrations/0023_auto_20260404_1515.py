from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0022_auto_20260403_2226')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Update',
            name='draft',
            field=fields.ForeignKeyField('models.MessageDraft', source_field='draft_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.SET_NULL),
        ),
    ]
