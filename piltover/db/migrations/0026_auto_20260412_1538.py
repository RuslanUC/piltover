from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0025_auto_20260408_1639')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='message_varchar',
            field=fields.CharField(null=True, db_index=True, max_length=8192),
        ),
        ops.RunSQL("UPDATE messagecontent SET message_varchar=message;"),
        ops.RemoveField(model_name='MessageContent', name='message'),
        ops.RenameField(model_name="MessageContent", old_name="message_varchar", new_name="message"),
    ]
