from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bcl", "0016_exammodule_listening_html_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="exammodule",
            name="content_file",
            field=models.FileField(
                blank=True,
                help_text="Optional module source file. Any file extension is accepted and browser-supported formats are displayed automatically.",
                null=True,
                upload_to="ielts/module-content/",
            ),
        ),
    ]
