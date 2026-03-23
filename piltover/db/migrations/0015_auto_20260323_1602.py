from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0014_auto_20260323_1533')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Channel',
            name='wallpaper',
            field=fields.ForeignKeyField('models.Wallpaper', source_field='wallpaper_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.SET_NULL),
        ),
    ]
