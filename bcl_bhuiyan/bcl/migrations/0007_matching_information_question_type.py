from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bcl", "0006_question_question_instructions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="question_type",
            field=models.CharField(
                choices=[
                    ("mcq", "Multiple Choice"),
                    ("tfng", "True / False / Not Given"),
                    ("ynng", "Yes / No / Not Given"),
                    ("fill_blank", "Fill in the Blank"),
                    ("short_answer", "Short Answer"),
                    ("matching", "Matching"),
                    ("matching_information", "Matching Information"),
                    ("essay", "Writing Task"),
                ],
                max_length=30,
            ),
        ),
    ]
