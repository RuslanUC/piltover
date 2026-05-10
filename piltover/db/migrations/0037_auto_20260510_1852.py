from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0036_auto_20260507_1620')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Stickerset',
            name='stickers_count',
            field=fields.SmallIntField(default=0),
        ),
        ops.AlterField(
            model_name='StickersetThumb',
            name='set',
            field=fields.OneToOneField('models.Stickerset', source_field='set_id', db_constraint=True, to_field='id', related_name='thumb', on_delete=OnDelete.CASCADE),
        ),
    ]
