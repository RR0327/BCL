from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bcl", "0007_matching_information_question_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="questionoption",
            name="option_text",
            field=models.CharField(
                blank=True,
                help_text="Optional description shown beside the option key.",
                max_length=500,
            ),
        ),
    ]
