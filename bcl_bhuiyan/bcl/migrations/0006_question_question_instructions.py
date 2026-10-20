from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bcl", "0005_examsection_passage_instructions"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="question_instructions",
            field=models.TextField(
                blank=True,
                help_text="Optional instructions shown directly above this question.",
            ),
        ),
    ]
