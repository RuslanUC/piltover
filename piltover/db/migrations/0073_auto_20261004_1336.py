from tortoise import migrations
from tortoise.migrations import operations as ops
from piltover.db.enums import ScheduledTaskState, ScheduledTaskType
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0072_auto_20260915_1001')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ScheduledTask',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('type', fields.IntEnumField(description='', enum_type=ScheduledTaskType, generated=False)),
                ('state', fields.IntEnumField(description='', enum_type=ScheduledTaskState, generated=False)),
                ('scheduled_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('next_attempt_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('generation', fields.SmallIntField(default=0)),
                ('message', fields.ForeignKeyField('models.MessageRef', source_field='message_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('extra_info', fields.BinaryField(null=True)),
            ],
            options={'table': 'scheduledtask', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.DeleteModel(name='TaskIqScheduledDeleteMessage'),
        ops.DeleteModel(name='TaskIqScheduledMessage'),
    ]
