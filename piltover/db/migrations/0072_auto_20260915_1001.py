from uuid import uuid4

from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0071_auto_20260915_0957')]

    initial = False

    operations = [
        ops.CreateModel(
            name='UploadingFileBig',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('file_id', fields.BigIntField()),
                ('physical_id', fields.UUIDField(default=uuid4)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('mime', fields.CharField(null=True, max_length=64)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('total_parts', fields.IntField(default=0)),
                ('part_size', fields.IntField(default=0)),
            ],
            options={'table': 'uploadingfilebig', 'app': 'models', 'unique_together': (('user', 'file_id'),), 'pk_attr': 'id'},
            bases=['UploadingFileBase'],
        ),
        ops.CreateModel(
            name='UploadingFileBigPart',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('part_id', fields.IntField()),
                ('physical_id', fields.UUIDField(default=uuid4)),
                ('size', fields.IntField()),
                ('file', fields.ForeignKeyField('models.UploadingFileBig', source_field='file_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'uploadingfilebigpart', 'app': 'models', 'unique_together': (('file', 'part_id'),), 'pk_attr': 'id'},
            bases=['UploadingFilePartBase'],
        ),
        ops.CreateModel(
            name='UploadingFileSmall',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('file_id', fields.BigIntField()),
                ('physical_id', fields.UUIDField(default=uuid4)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('mime', fields.CharField(null=True, max_length=64)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'uploadingfilesmall', 'app': 'models', 'unique_together': (('user', 'file_id'),), 'pk_attr': 'id'},
            bases=['UploadingFileBase'],
        ),
        ops.CreateModel(
            name='UploadingFileSmallPart',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('part_id', fields.IntField()),
                ('physical_id', fields.UUIDField(default=uuid4)),
                ('size', fields.IntField()),
                ('file', fields.ForeignKeyField('models.UploadingFileSmall', source_field='file_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'uploadingfilesmallpart', 'app': 'models', 'unique_together': (('file', 'part_id'),), 'pk_attr': 'id'},
            bases=['UploadingFilePartBase'],
        ),
    ]
