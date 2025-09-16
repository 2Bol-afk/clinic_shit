from django.db import migrations, models
import django.conf
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('visits', '0008_visit_lab_arrived'),
        migrations.swappable_dependency(django.conf.settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='lab_claimed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='visit',
            name='lab_claimed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='claimed_lab_visits', to=django.conf.settings.AUTH_USER_MODEL),
        ),
    ]


