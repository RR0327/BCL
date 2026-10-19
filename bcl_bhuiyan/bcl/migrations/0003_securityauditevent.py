from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):
    dependencies = [('bcl', '0002_writingtaskevaluation_and_more')]
    operations = [migrations.CreateModel(name='SecurityAuditEvent', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('occurred_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
        ('event', models.CharField(db_index=True, max_length=64)),
        ('actor_id', models.PositiveBigIntegerField(blank=True, null=True)),
        ('subject_id', models.PositiveBigIntegerField(blank=True, null=True)),
        ('object_id', models.PositiveBigIntegerField(blank=True, null=True)),
        ('outcome', models.CharField(default='success', max_length=16)),
    ], options={'ordering': ['-occurred_at']})]
