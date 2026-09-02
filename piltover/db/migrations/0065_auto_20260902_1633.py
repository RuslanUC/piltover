from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0064_auto_20260814_1749')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Dialog',
            name='last_read_message_id',
            field=fields.BigIntField(default=0),
        ),
        ops.RunSQL(
            """
            UPDATE 
                dialog d 
            SET 
                last_read_message_id = COALESCE(
                    (
                        SELECT rs.last_message_id 
                        FROM readstate rs 
                        WHERE rs.owner_id = d.owner_id AND rs.peer_id = d.peer_id
                    ), 
                    0
                );
            """
        ),
        ops.DeleteModel(name='ReadState'),
    ]
