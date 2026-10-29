from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0072_auto_20260915_1001')]

    initial = False

    operations = [
        ops.CreateModel(
            name='WebpageMetadata',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('url', fields.CharField(max_length=512)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('pending', fields.BooleanField(default=True)),
                ('title', fields.CharField(null=True, max_length=128)),
                ('site_name', fields.CharField(null=True, max_length=64)),
                ('description', fields.CharField(null=True, max_length=512)),
                ('image', fields.ForeignKeyField('models.File', source_field='image_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'webpagemetadata', 'app': 'models', 'indexes': [Index(fields=['url', 'created_at'])], 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
