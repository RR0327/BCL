from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bcl", "0004_question_answer_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="examsection",
            name="passage_instructions",
            field=models.TextField(
                blank=True,
                help_text="Instructions or introductory text shown with the passage.",
            ),
        ),
    ]
