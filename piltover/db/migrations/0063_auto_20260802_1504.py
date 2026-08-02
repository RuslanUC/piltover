from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0062_auto_20260802_1333')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Contact',
            name='personal_photo',
            field=fields.ForeignKeyField('models.File', source_field='personal_photo_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
