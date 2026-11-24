import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

DISTRICTS = [('thiruvananthapuram', 'Thiruvananthapuram'), ('kollam', 'Kollam'), ('pathanamthitta', 'Pathanamthitta'), ('alappuzha', 'Alappuzha'), ('kottayam', 'Kottayam'), ('idukki', 'Idukki'), ('ernakulam', 'Ernakulam'), ('thrissur', 'Thrissur'), ('palakkad', 'Palakkad'), ('malappuram', 'Malappuram'), ('kozhikode', 'Kozhikode'), ('wayanad', 'Wayanad'), ('kannur', 'Kannur'), ('kasaragod', 'Kasaragod')]
DONATION_TYPES = [('whole_blood', 'Whole blood'), ('platelets', 'Platelets'), ('plasma', 'Plasma')]


def import_existing_donation_dates(apps, schema_editor):
    """Keep every existing donor's last donation date as a history record."""
    DonorProfile = apps.get_model('core', 'DonorProfile')
    DonationRecord = apps.get_model('core', 'DonationRecord')
    for donor in DonorProfile.objects.exclude(last_donation_date__isnull=True):
        DonationRecord.objects.get_or_create(
            donor=donor, donation_date=donor.last_donation_date, status='completed',
            defaults={'source': 'migration', 'donation_type': 'whole_blood'},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── DonorProfile ──
        migrations.AddField(model_name='donorprofile', name='date_of_birth', field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='donorprofile', name='next_eligible_date', field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='donorprofile', name='eligibility_hold', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='donorprofile', name='hold_reason', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='donorprofile', name='health_declaration', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='donorprofile', name='notify_reminders', field=models.BooleanField(default=True)),

        # ── DonorContactRequest ──
        migrations.AlterField(
            model_name='donorcontactrequest', name='status',
            field=models.CharField(choices=[('initiated', 'Call Initiated'), ('not_connected', 'Receiver Not Connected'), ('receiver_confirmed', 'Receiver Confirmed Call'), ('donor_confirmed', 'Donor Confirmed Willingness'), ('donor_declined', 'Donor Declined'), ('hospital_selected', 'Hospital Selected'), ('whatsapp_sent', 'WhatsApp Confirmation Sent (legacy)'), ('location_sent', 'Hospital Location Sent'), ('expired', 'Expired')], default='initiated', max_length=30),
        ),
        migrations.AddField(model_name='donorcontactrequest', name='receiver_ack', field=models.BooleanField(default=False)),

        # ── HospitalLocationDetails ──
        migrations.AlterField(model_name='hospitallocationdetails', name='district', field=models.CharField(blank=True, choices=DISTRICTS, max_length=50)),
        migrations.AddField(model_name='hospitallocationdetails', name='latitude', field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name='hospitallocationdetails', name='longitude', field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name='hospitallocationdetails', name='place_id', field=models.CharField(blank=True, max_length=300)),

        # ── Notification ──
        migrations.AlterField(
            model_name='notification', name='notification_type',
            field=models.CharField(choices=[('call_initiated', 'Call Initiated'), ('call_confirmed', 'Call Confirmed'), ('donor_confirmed', 'Donor Confirmed'), ('donor_declined', 'Donor Declined'), ('whatsapp_sent', 'WhatsApp Sent'), ('location_shared', 'Location Shared'), ('donor_request', 'Donor Request'), ('reminder', 'Donation Reminder'), ('general', 'General')], default='general', max_length=30),
        ),

        # ── New models ──
        migrations.CreateModel(
            name='EligibilitySettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('whole_blood_interval_days', models.PositiveIntegerField(default=90)),
                ('platelet_interval_days', models.PositiveIntegerField(default=90)),
                ('plasma_interval_days', models.PositiveIntegerField(default=90)),
                ('no_history_policy', models.CharField(choices=[('available', 'Available if the donor has made the health declaration'), ('unavailable', 'Unavailable until a donation date is recorded')], default='available', max_length=20)),
                ('reminder_days_before', models.PositiveIntegerField(default=7)),
                ('interval_validated_by', models.CharField(blank=True, max_length=200)),
                ('interval_validated_on', models.DateField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Eligibility Settings', 'verbose_name_plural': 'Eligibility Settings'},
        ),
        migrations.CreateModel(
            name='DonationRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('donation_date', models.DateField()),
                ('donation_type', models.CharField(choices=DONATION_TYPES, default='whole_blood', max_length=20)),
                ('status', models.CharField(choices=[('completed', 'Completed'), ('cancelled', 'Cancelled (admin correction)')], default='completed', max_length=20)),
                ('next_eligible_date', models.DateField(blank=True, null=True)),
                ('source', models.CharField(choices=[('self', 'Donor'), ('registration', 'Registration'), ('admin', 'Administrator'), ('migration', 'Imported from earlier data')], default='self', max_length=20)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('donor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='donations', to='core.donorprofile')),
            ],
            options={'verbose_name': 'Donation Record', 'verbose_name_plural': 'Donation Records', 'ordering': ['-donation_date', '-id']},
        ),
        migrations.AddConstraint(
            model_name='donationrecord',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'completed')), fields=('donor', 'donation_date'), name='uniq_completed_donation_per_day'),
        ),
        migrations.CreateModel(
            name='Reminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_date', models.DateField()),
                ('remind_on', models.DateField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('sent', 'Sent'), ('cancelled', 'Cancelled / replaced'), ('skipped', 'Skipped (notifications off)')], default='pending', max_length=20)),
                ('push_status', models.CharField(blank=True, max_length=100)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('donor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to='core.donorprofile')),
                ('notification', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reminders', to='core.notification')),
            ],
            options={'verbose_name': 'Reminder', 'verbose_name_plural': 'Reminders', 'ordering': ['remind_on']},
        ),
        migrations.AddConstraint(
            model_name='reminder',
            constraint=models.UniqueConstraint(fields=('donor', 'target_date'), name='uniq_reminder_per_target'),
        ),
        migrations.CreateModel(
            name='PushSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('endpoint', models.CharField(max_length=700, unique=True)),
                ('p256dh', models.CharField(max_length=255)),
                ('auth', models.CharField(max_length=255)),
                ('user_agent', models.CharField(blank=True, max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('failure_count', models.PositiveIntegerField(default=0)),
                ('last_error', models.TextField(blank=True)),
                ('last_success_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='push_subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Push Subscription', 'verbose_name_plural': 'Push Subscriptions'},
        ),
        migrations.RunPython(import_existing_donation_dates, migrations.RunPython.noop),
    ]
