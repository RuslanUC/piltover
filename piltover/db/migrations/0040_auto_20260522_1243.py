from tortoise import migrations
from tortoise.migrations import operations as ops
from piltover.db.enums import StickerSetOfficialType
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0039_auto_20260515_1905')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='Stickerset',
            name='official_type',
            field=fields.IntEnumField(null=True, db_index=True, description='', enum_type=StickerSetOfficialType, generated=False),
        ),
    ]
