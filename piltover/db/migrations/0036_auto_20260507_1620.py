from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields
from tortoise.migrations.constraints import UniqueConstraint

class Migration(migrations.Migration):
    dependencies = [('models', '0035_auto_20260506_1624')]

    initial = False

    operations = [
        ops.RemoveConstraint(
            model_name='MessageRef',
            name=None,
            fields=['peer', 'random_id'],
        ),
        ops.AddField(
            model_name='MessageRef',
            name='random_user',
            field=fields.ForeignKeyField('models.User', source_field='random_user_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AddConstraint(
            model_name='MessageRef',
            constraint=UniqueConstraint(fields=('peer', 'random_id', 'random_user'), name=None),
        ),
    ]
