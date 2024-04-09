# Generated by Django 3.2.20 on 2024-04-09 13:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_design_builder", "0007_design_description"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="designinstance",
            options={"verbose_name": "Design Deployment", "verbose_name_plural": "Design Deployments"},
        ),
        migrations.AddField(
            model_name="design",
            name="docs",
            field=models.CharField(blank=True, default="", editable=False, max_length=4096),
        ),
        migrations.AlterField(
            model_name="design",
            name="description",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="design",
            name="version",
            field=models.CharField(default="0.0.0", max_length=20),
        ),
    ]
