"""
Core models for Sanjeevani Blood Donor Connection Platform.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import RegexValidator
from datetime import date

from . import eligibility

# Kerala Districts
KERALA_DISTRICTS = [
    ('thiruvananthapuram', 'Thiruvananthapuram'),
    ('kollam', 'Kollam'),
    ('pathanamthitta', 'Pathanamthitta'),
    ('alappuzha', 'Alappuzha'),
    ('kottayam', 'Kottayam'),
    ('idukki', 'Idukki'),
    ('ernakulam', 'Ernakulam'),
    ('thrissur', 'Thrissur'),
    ('palakkad', 'Palakkad'),
    ('malappuram', 'Malappuram'),
    ('kozhikode', 'Kozhikode'),
    ('wayanad', 'Wayanad'),
    ('kannur', 'Kannur'),
    ('kasaragod', 'Kasaragod'),
]

BLOOD_GROUPS = [
    ('A+', 'A+'),
    ('A-', 'A-'),
    ('B+', 'B+'),
    ('B-', 'B-'),
    ('AB+', 'AB+'),
    ('AB-', 'AB-'),
    ('O+', 'O+'),
    ('O-', 'O-'),
]

phone_validator = RegexValidator(
    regex=r'^[6-9]\d{9}$',
    message='Enter a valid 10-digit Indian mobile number.'
)


class DonorQuerySet(models.QuerySet):
    def searchable(self):
        """Donors shown publicly: active, opted-in and verified as 18+ (DOB on file)."""
        return self.filter(
            is_active=True, show_in_directory=True,
            date_of_birth__isnull=False,
            date_of_birth__lte=eligibility.adult_cutoff(),
        )


class DonorProfile(models.Model):
    """Extended profile for blood donors."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='donor_profile')
    mobile = models.CharField(max_length=10, unique=True, validators=[phone_validator])
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUPS)
    district = models.CharField(max_length=50, choices=KERALA_DISTRICTS)
    locality = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    last_donation_date = models.DateField(null=True, blank=True)
    next_eligible_date = models.DateField(null=True, blank=True)
    # is_available is now calculated automatically (see core.services.recalc_donor)
    is_available = models.BooleanField(default=True)
    eligibility_hold = models.BooleanField(default=False)
    hold_reason = models.CharField(max_length=200, blank=True)
    health_declaration = models.BooleanField(default=False)
    notify_reminders = models.BooleanField(default=True)
    show_in_directory = models.BooleanField(default=True)
    share_contact = models.BooleanField(default=True)
    show_last_donation_date = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DonorQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.blood_group} ({self.district})"

    @property
    def age(self):
        return eligibility.calculate_age(self.date_of_birth) if self.date_of_birth else None

    @property
    def is_verified_adult(self):
        return eligibility.is_adult(self.date_of_birth)

    def get_display_name(self):
        return self.user.get_full_name() or self.user.username

    def get_whatsapp_number(self):
        """Return number formatted for WhatsApp (91 + mobile)."""
        return f"91{self.mobile}"

    def can_donate(self):
        """Current availability as calculated by the eligibility rules."""
        return self.is_available

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Donor Profile'
        verbose_name_plural = 'Donor Profiles'


class DonorContactRequest(models.Model):
    """Tracks when a receiver contacts a donor."""
    STATUS_CHOICES = [
        ('initiated', 'Call Initiated'),
        ('not_connected', 'Receiver Not Connected'),
        ('receiver_confirmed', 'Receiver Confirmed Call'),
        ('donor_confirmed', 'Donor Confirmed Willingness'),
        ('donor_declined', 'Donor Declined'),
        ('hospital_selected', 'Hospital Selected'),
        ('whatsapp_sent', 'WhatsApp Confirmation Sent (legacy)'),
        ('location_sent', 'Hospital Location Sent'),
        ('expired', 'Expired'),
    ]

    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contact_requests_made')
    donor_profile = models.ForeignKey(DonorProfile, on_delete=models.CASCADE, related_name='contact_requests_received')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='initiated')
    receiver_confirmed_call = models.BooleanField(default=False)
    receiver_confirmed_at = models.DateTimeField(null=True, blank=True)
    donor_responded = models.BooleanField(default=False)
    donor_response_at = models.DateTimeField(null=True, blank=True)
    whatsapp_opened = models.BooleanField(default=False)
    whatsapp_opened_at = models.DateTimeField(null=True, blank=True)
    location_whatsapp_opened = models.BooleanField(default=False)
    location_whatsapp_opened_at = models.DateTimeField(null=True, blank=True)
    receiver_ack = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.receiver.username} → {self.donor_profile} [{self.status}]"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Donor Contact Request'
        verbose_name_plural = 'Donor Contact Requests'


class HospitalLocationDetails(models.Model):
    """Hospital location shared by receiver to donor."""
    contact_request = models.OneToOneField(
        DonorContactRequest, on_delete=models.CASCADE, related_name='hospital_location'
    )
    hospital_name = models.CharField(max_length=200)
    district = models.CharField(max_length=50, choices=KERALA_DISTRICTS, blank=True)
    full_address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    place_id = models.CharField(max_length=300, blank=True)
    google_maps_link = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.hospital_name} - {self.contact_request}"

    class Meta:
        verbose_name = 'Hospital Location'
        verbose_name_plural = 'Hospital Locations'


class Notification(models.Model):
    """In-app notifications for donors and receivers."""
    NOTIF_TYPES = [
        ('call_initiated', 'Call Initiated'),
        ('call_confirmed', 'Call Confirmed'),
        ('donor_confirmed', 'Donor Confirmed'),
        ('donor_declined', 'Donor Declined'),
        ('whatsapp_sent', 'WhatsApp Sent'),
        ('location_shared', 'Location Shared'),
        ('donor_request', 'Donor Request'),
        ('reminder', 'Donation Reminder'),
        ('general', 'General'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    contact_request = models.ForeignKey(
        DonorContactRequest, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications'
    )
    notification_type = models.CharField(max_length=30, choices=NOTIF_TYPES, default='general')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}: {self.title}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'


class ContactMessage(models.Model):
    """Contact form submissions."""
    name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.CharField(max_length=10, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.subject}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Contact Message'
        verbose_name_plural = 'Contact Messages'


class AbuseReport(models.Model):
    """Reports of inappropriate donor profiles."""
    reporter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reported_donor = models.ForeignKey(DonorProfile, on_delete=models.CASCADE, related_name='abuse_reports')
    reason = models.TextField()
    is_reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report on {self.reported_donor} by {self.reporter}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Abuse Report'
        verbose_name_plural = 'Abuse Reports'


class ActivityLog(models.Model):
    """System activity log for admin monitoring."""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} at {self.created_at}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'


DONATION_TYPES = [
    ('whole_blood', 'Whole blood'),
    ('platelets', 'Platelets'),
    ('plasma', 'Plasma'),
]


class EligibilitySettings(models.Model):
    """Single-row, admin-editable eligibility policy (no hardcoded medical period)."""
    NO_HISTORY_CHOICES = [
        ('available', 'Available if the donor has made the health declaration'),
        ('unavailable', 'Unavailable until a donation date is recorded'),
    ]
    whole_blood_interval_days = models.PositiveIntegerField(default=90)
    platelet_interval_days = models.PositiveIntegerField(default=90)
    plasma_interval_days = models.PositiveIntegerField(default=90)
    no_history_policy = models.CharField(max_length=20, choices=NO_HISTORY_CHOICES, default='available')
    reminder_days_before = models.PositiveIntegerField(default=7)
    interval_validated_by = models.CharField(max_length=200, blank=True)
    interval_validated_on = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Eligibility Settings'
        verbose_name_plural = 'Eligibility Settings'

    def __str__(self):
        return 'Eligibility settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def interval_for(self, donation_type):
        return {
            'platelets': self.platelet_interval_days,
            'plasma': self.plasma_interval_days,
        }.get(donation_type, self.whole_blood_interval_days)

    @property
    def is_validated(self):
        return bool(self.interval_validated_by and self.interval_validated_on)


class DonationRecord(models.Model):
    """One completed (or cancelled/corrected) donation in a donor's history."""
    STATUS_CHOICES = [('completed', 'Completed'), ('cancelled', 'Cancelled (admin correction)')]
    SOURCE_CHOICES = [
        ('self', 'Donor'), ('registration', 'Registration'),
        ('admin', 'Administrator'), ('migration', 'Imported from earlier data'),
    ]
    donor = models.ForeignKey(DonorProfile, on_delete=models.CASCADE, related_name='donations')
    donation_date = models.DateField()
    donation_type = models.CharField(max_length=20, choices=DONATION_TYPES, default='whole_blood')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    next_eligible_date = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='self')
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-donation_date', '-id']
        verbose_name = 'Donation Record'
        verbose_name_plural = 'Donation Records'
        constraints = [
            models.UniqueConstraint(
                fields=['donor', 'donation_date'],
                condition=models.Q(status='completed'),
                name='uniq_completed_donation_per_day',
            ),
        ]

    def __str__(self):
        return f"{self.donor} - {self.donation_date} ({self.status})"


class Reminder(models.Model):
    """Server-side scheduled 'next eligible date is approaching' reminder."""
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('processing', 'Processing'), ('sent', 'Sent'),
        ('cancelled', 'Cancelled / replaced'), ('skipped', 'Skipped (notifications off)'),
    ]
    donor = models.ForeignKey(DonorProfile, on_delete=models.CASCADE, related_name='reminders')
    target_date = models.DateField()
    remind_on = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    push_status = models.CharField(max_length=100, blank=True)
    notification = models.ForeignKey(
        Notification, on_delete=models.SET_NULL, null=True, blank=True, related_name='reminders'
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['remind_on']
        verbose_name = 'Reminder'
        verbose_name_plural = 'Reminders'
        constraints = [
            models.UniqueConstraint(fields=['donor', 'target_date'], name='uniq_reminder_per_target'),
        ]

    def __str__(self):
        return f"Reminder for {self.donor} on {self.remind_on} [{self.status}]"


class PushSubscription(models.Model):
    """Browser Web Push subscription (VAPID)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.CharField(max_length=700, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    failure_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Push Subscription'
        verbose_name_plural = 'Push Subscriptions'

    def __str__(self):
        return f"{self.user.username} push ({'active' if self.is_active else 'inactive'})"
