from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bcl", "0017_exammodule_content_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="exammodule",
            name="module_file",
            field=models.FileField(
                blank=True,
                help_text="Optional file for this module. Any file extension is accepted.",
                null=True,
                upload_to="ielts/module-files/",
            ),
        ),
    ]
