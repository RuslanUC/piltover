from tortoise import migrations
from tortoise.backends.base.schema_generator import BaseSchemaGenerator
from tortoise.migrations import operations as ops


_schema_generator = BaseSchemaGenerator(None)
dialog_fk_name = _schema_generator._get_fk_name("dialog", "peer_id", "peer", "id")
draft_fk_name = _schema_generator._get_fk_name("messagedraft", "peer_id", "peer", "id")
readstate_fk_name = _schema_generator._get_fk_name("readstate", "peer_id", "peer", "id")
saveddialog_fk_name = _schema_generator._get_fk_name("saveddialog", "peer_id", "peer", "id")


class Migration(migrations.Migration):
    dependencies = [('models', '0043_fill_channel_peers_20260522_1459')]

    initial = False
    atomic = False

    operations = [
        ops.RunSQL(f"ALTER TABLE dialog DROP FOREIGN KEY {dialog_fk_name}"),
        ops.RunSQL("ALTER TABLE dialog DROP INDEX peer_id"),
        ops.RunSQL("ALTER TABLE dialog ADD INDEX {dialog_fk_name} (peer_id)"),
        ops.RunSQL(f"ALTER TABLE dialog ADD CONSTRAINT {dialog_fk_name} FOREIGN KEY (peer_id) REFERENCES peer(id) ON DELETE CASCADE"),

        ops.RunSQL(f"ALTER TABLE messagedraft DROP FOREIGN KEY {draft_fk_name}"),
        ops.RunSQL("ALTER TABLE messagedraft DROP INDEX peer_id"),
        ops.RunSQL("ALTER TABLE messagedraft ADD INDEX {draft_fk_name} (peer_id)"),
        ops.RunSQL(f"ALTER TABLE messagedraft ADD CONSTRAINT {draft_fk_name} FOREIGN KEY (peer_id) REFERENCES peer(id) ON DELETE CASCADE"),

        ops.RunSQL(f"ALTER TABLE readstate DROP FOREIGN KEY {readstate_fk_name}"),
        ops.RunSQL("ALTER TABLE readstate DROP INDEX peer_id"),
        ops.RunSQL("ALTER TABLE readstate ADD INDEX {readstate_fk_name} (peer_id)"),
        ops.RunSQL(f"ALTER TABLE readstate ADD CONSTRAINT {readstate_fk_name} FOREIGN KEY (peer_id) REFERENCES peer(id) ON DELETE CASCADE"),

        ops.RunSQL(f"ALTER TABLE saveddialog DROP FOREIGN KEY {saveddialog_fk_name}"),
        ops.RunSQL("ALTER TABLE saveddialog DROP INDEX peer_id"),
        ops.RunSQL("ALTER TABLE saveddialog ADD INDEX {saveddialog_fk_name} (peer_id)"),
        ops.RunSQL(f"ALTER TABLE saveddialog ADD CONSTRAINT {saveddialog_fk_name} FOREIGN KEY (peer_id) REFERENCES peer(id) ON DELETE CASCADE"),

        # ops.AlterField(
        #     model_name='Dialog',
        #     name='peer',
        #     field=fields.ForeignKeyField('models.Peer', source_field='peer_id', to_field='id', on_delete=OnDelete.CASCADE),
        # ),
        # ops.AlterField(
        #     model_name='MessageDraft',
        #     name='peer',
        #     field=fields.ForeignKeyField('models.Peer', source_field='peer_id', to_field='id', on_delete=OnDelete.CASCADE),
        # ),
        # ops.AlterField(
        #     model_name='ReadState',
        #     name='peer',
        #     field=fields.ForeignKeyField('models.Peer', source_field='peer_id', to_field='id', on_delete=OnDelete.CASCADE),
        # ),
        # ops.AlterField(
        #     model_name='SavedDialog',
        #     name='peer',
        #     field=fields.ForeignKeyField('models.Peer', source_field='peer_id', to_field='id', on_delete=OnDelete.CASCADE),
        # ),
    ]
