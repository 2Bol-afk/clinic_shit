from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('visits', '0009_visit_lab_claim_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='doctor_arrived',
            field=models.BooleanField(default=False),
        ),
    ]


