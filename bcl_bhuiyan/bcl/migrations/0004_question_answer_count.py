from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bcl", "0003_securityauditevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="answer_count",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Number of answer fields for fill-in-the-blank questions. Use ___ in the prompt for inline fields.",
            ),
        ),
    ]
