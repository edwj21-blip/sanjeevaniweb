"""
Core models for Sanjeevani Blood Donor Connection Platform.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import RegexValidator

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


class DonorProfile(models.Model):
    """Extended profile for blood donors."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='donor_profile')
    mobile = models.CharField(max_length=10, unique=True, validators=[phone_validator])
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUPS)
    district = models.CharField(max_length=50, choices=KERALA_DISTRICTS)
    locality = models.CharField(max_length=100)
    last_donation_date = models.DateField(null=True, blank=True)
    is_available = models.BooleanField(default=True)
    show_in_directory = models.BooleanField(default=True)
    share_contact = models.BooleanField(default=True)
    show_last_donation_date = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.blood_group} ({self.district})"

    def get_display_name(self):
        return self.user.get_full_name() or self.user.username

    def get_whatsapp_number(self):
        """Return number formatted for WhatsApp (91 + mobile)."""
        return f"91{self.mobile}"

    def can_donate(self):
        """Check if donor can donate (3 months since last donation)."""
        if not self.last_donation_date:
            return True
        from datetime import date, timedelta
        return (date.today() - self.last_donation_date).days >= 90

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Donor Profile'
        verbose_name_plural = 'Donor Profiles'


class DonorContactRequest(models.Model):
    """Tracks when a receiver contacts a donor."""
    STATUS_CHOICES = [
        ('initiated', 'Call Initiated'),
        ('receiver_confirmed', 'Receiver Confirmed Call'),
        ('donor_confirmed', 'Donor Confirmed Willingness'),
        ('donor_declined', 'Donor Declined'),
        ('whatsapp_sent', 'WhatsApp Confirmation Sent'),
        ('location_sent', 'Hospital Location Sent'),
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
    district = models.CharField(max_length=50, choices=KERALA_DISTRICTS)
    full_address = models.TextField()
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
