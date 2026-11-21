"""Admin configuration for Sanjeevani."""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    DonorProfile, DonorContactRequest, HospitalLocationDetails,
    Notification, ContactMessage, AbuseReport, ActivityLog
)


@admin.register(DonorProfile)
class DonorProfileAdmin(admin.ModelAdmin):
    list_display = ['get_name', 'blood_group', 'district', 'locality', 'mobile', 'is_available', 'is_active', 'created_at']
    list_filter = ['blood_group', 'district', 'is_available', 'is_active', 'show_in_directory']
    search_fields = ['user__first_name', 'user__last_name', 'mobile', 'locality']
    list_editable = ['is_available', 'is_active']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    get_name.short_description = 'Name'

    actions = ['activate_donors', 'deactivate_donors']

    def activate_donors(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, 'Selected donors activated.')
    activate_donors.short_description = 'Activate selected donors'

    def deactivate_donors(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, 'Selected donors deactivated.')
    deactivate_donors.short_description = 'Deactivate selected donors'


@admin.register(DonorContactRequest)
class DonorContactRequestAdmin(admin.ModelAdmin):
    list_display = ['receiver', 'donor_profile', 'status', 'receiver_confirmed_call', 'donor_responded', 'created_at']
    list_filter = ['status', 'receiver_confirmed_call', 'donor_responded']
    search_fields = ['receiver__username', 'donor_profile__user__first_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(HospitalLocationDetails)
class HospitalLocationAdmin(admin.ModelAdmin):
    list_display = ['hospital_name', 'district', 'contact_request', 'created_at']
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
