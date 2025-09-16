from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('visits', '0010_visit_doctor_arrived'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='doctor_status',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
    ]


