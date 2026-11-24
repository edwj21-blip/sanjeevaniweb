"""Admin configuration for Sanjeevani."""
from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages as dj_messages
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import (
    DonorProfile, DonorContactRequest, HospitalLocationDetails,
    Notification, ContactMessage, AbuseReport, ActivityLog,
    DonationRecord, EligibilitySettings, Reminder, PushSubscription,
)
from .services import recalc_donor, recalc_all


class DonationRecordInline(admin.TabularInline):
    model = DonationRecord
    extra = 0
    fields = ['donation_date', 'donation_type', 'status', 'next_eligible_date', 'source', 'note']
    readonly_fields = ['next_eligible_date']
    can_delete = False


@admin.register(DonorProfile)
class DonorProfileAdmin(admin.ModelAdmin):
    list_display = ['get_name', 'blood_group', 'district', 'locality', 'mobile', 'age_display',
                    'is_available', 'next_eligible_date', 'eligibility_hold', 'is_active', 'created_at']
    list_filter = ['blood_group', 'district', 'is_available', 'eligibility_hold', 'is_active', 'show_in_directory']
    search_fields = ['user__first_name', 'user__last_name', 'mobile', 'locality']
    list_editable = ['is_active', 'eligibility_hold']
    readonly_fields = ['is_available', 'next_eligible_date', 'last_donation_date', 'created_at', 'updated_at']
    ordering = ['-created_at']
    inlines = [DonationRecordInline]
    actions = ['activate_donors', 'deactivate_donors', 'recalculate']

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    get_name.short_description = 'Name'

    def age_display(self, obj):
        return obj.age if obj.age is not None else 'DOB missing'
    age_display.short_description = 'Age'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            recalc_donor(obj)                # also covers list_editable changes

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        recalc_donor(form.instance)          # status is always derived, never typed in

    def has_delete_permission(self, request, obj=None):
        return False                          # donor records are never deleted

    def activate_donors(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, 'Selected donors activated.')

    def deactivate_donors(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, 'Selected donors deactivated.')

    def recalculate(self, request, queryset):
        for d in queryset:
            recalc_donor(d)
        self.message_user(request, 'Availability recalculated.')
    recalculate.short_description = 'Recalculate availability'


@admin.register(DonationRecord)
class DonationRecordAdmin(admin.ModelAdmin):
    list_display = ['donor', 'donation_date', 'donation_type', 'status', 'next_eligible_date', 'source', 'created_at']
    list_filter = ['status', 'donation_type', 'source']
    search_fields = ['donor__user__first_name', 'donor__mobile']
    readonly_fields = ['created_at']
    date_hierarchy = 'donation_date'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.source = 'admin'
        super().save_model(request, obj, form, change)
        recalc_donor(obj.donor)

    def has_delete_permission(self, request, obj=None):
        return False   # correct mistakes by setting status to "cancelled"


@admin.register(EligibilitySettings)
class EligibilitySettingsAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'whole_blood_interval_days', 'platelet_interval_days', 'plasma_interval_days',
                    'no_history_policy', 'reminder_days_before', 'interval_validated_by', 'interval_validated_on']
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        return not EligibilitySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        n = recalc_all()
        dj_messages.info(request, f'Availability recalculated for {n} donors using the new settings.')


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ['donor', 'target_date', 'remind_on', 'status', 'push_status', 'sent_at']
    list_filter = ['status']
    readonly_fields = ['created_at', 'sent_at', 'notification']


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_active', 'failure_count', 'last_success_at', 'created_at']
    list_filter = ['is_active']
    exclude = ['p256dh', 'auth', 'endpoint']
    readonly_fields = ['created_at', 'last_success_at', 'last_error', 'user_agent']

    def has_add_permission(self, request):
        return False


@admin.register(DonorContactRequest)
class DonorContactRequestAdmin(admin.ModelAdmin):
    list_display = ['receiver', 'donor_profile', 'status', 'receiver_confirmed_call', 'donor_responded', 'created_at']
    list_filter = ['status', 'receiver_confirmed_call', 'donor_responded']
    search_fields = ['receiver__username', 'donor_profile__user__first_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(HospitalLocationDetails)
class HospitalLocationAdmin(admin.ModelAdmin):
    list_display = ['hospital_name', 'latitude', 'longitude', 'contact_request', 'created_at']
    search_fields = ['hospital_name', 'full_address']
    readonly_fields = ['created_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['user__username', 'title']
    readonly_fields = ['created_at']


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'subject', 'is_resolved', 'created_at']
    list_filter = ['is_resolved']
    search_fields = ['name', 'email', 'subject']
    list_editable = ['is_resolved']
    readonly_fields = ['created_at']


@admin.register(AbuseReport)
class AbuseReportAdmin(admin.ModelAdmin):
    list_display = ['reporter', 'reported_donor', 'is_reviewed', 'created_at']
    list_filter = ['is_reviewed']
    list_editable = ['is_reviewed']
    readonly_fields = ['created_at']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'ip_address', 'created_at']
    list_filter = ['action']
    search_fields = ['user__username', 'action']
    readonly_fields = ['created_at']

    def has_add_permission(self, request):
        return False


# Customize admin site
admin.site.site_header = 'Sanjeevani Administration'
admin.site.site_title = 'Sanjeevani Admin'
admin.site.index_title = 'Blood Donor Platform Management'
