from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0013_auto_20260322_1858')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Channel',
            name='emojiset',
            field=fields.ForeignKeyField('models.Stickerset', source_field='emojiset_id', null=True, db_constraint=True, to_field='id', related_name='channel_emojis', on_delete=OnDelete.SET_NULL),
        ),
    ]
