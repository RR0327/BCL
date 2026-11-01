from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bcl", "0015_alter_exammodule_audio_file_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="exammodule",
            name="listening_html_file",
            field=models.FileField(
                blank=True,
                help_text="Optional uploaded HTML listening test. Used for Listening modules without database sections.",
                null=True,
                upload_to="ielts/listening/",
                validators=[FileExtensionValidator(allowed_extensions=["html"])],
            ),
        ),
    ]
