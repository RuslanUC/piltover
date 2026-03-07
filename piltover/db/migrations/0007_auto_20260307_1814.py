from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields
from tortoise.migrations.constraints import UniqueConstraint

class Migration(migrations.Migration):
    dependencies = [('models', '0006_auto_20260304_1618')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='RecentReaction',
            name='reaction',
            field=fields.ForeignKeyField('models.Reaction', source_field='reaction_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AddField(
            model_name='RecentReaction',
            name='custom_emoji',
            field=fields.ForeignKeyField('models.File', source_field='custom_emoji_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AddConstraint(
            model_name='RecentReaction',
            constraint=UniqueConstraint(fields=('user', 'custom_emoji'), name=None),
        ),
    ]
