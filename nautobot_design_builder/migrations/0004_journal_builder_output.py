# Generated by Django 3.2.23 on 2024-01-19 06:41

from django.db import migrations, models
import nautobot.core.celery


class Migration(migrations.Migration):

    dependencies = [
        ('nautobot_design_builder', '0003_tune_design_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='journal',
            name='builder_output',
            field=models.JSONField(blank=True, editable=False, encoder=nautobot.core.celery.NautobotKombuJSONEncoder, null=True),
        ),
    ]
