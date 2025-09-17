from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('visits', '0012_servicetype_visit_service_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='status',
            field=models.CharField(choices=[('queued', 'Queued'), ('claimed', 'Claimed/In Process'), ('finished', 'Finished')], default='queued', max_length=16),
        ),
    ]


