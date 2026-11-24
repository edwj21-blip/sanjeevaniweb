"""URL configuration for core app."""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('set-language/', views.set_language_view, name='set_language'),
    path('sw.js', views.service_worker, name='service_worker'),

    # Authentication
    path('register/', views.donor_register, name='register'),
    path('signup/', views.receiver_signup, name='signup'),
    path('login/', views.donor_login, name='login'),
    path('logout/', views.donor_logout, name='logout'),

    # Find Blood (public)
    path('donors/', views.donor_directory, name='donor_directory'),
    path('find-blood/', views.donor_directory, name='find_blood'),
    path('donors/<int:donor_id>/', views.donor_detail, name='donor_detail'),

    # Call → confirm → donor popup → receiver popup (JSON, database backed)
    path('api/call-start/<int:donor_id>/', views.api_call_start, name='api_call_start'),
    path('api/call-confirm/<int:request_id>/', views.api_call_confirm, name='api_call_confirm'),
    path('api/respond/<int:request_id>/', views.api_respond, name='api_respond'),
    path('api/ack/<int:request_id>/', views.api_ack, name='api_ack'),
    path('api/poll/', views.api_poll, name='api_poll'),

    # Hospital selection (Google Maps) and WhatsApp location sharing
    path('hospital/<int:request_id>/', views.hospital_select, name='hospital_select'),
    path('hospital/<int:request_id>/save/', views.api_hospital_save, name='api_hospital_save'),
    path('hospital/<int:request_id>/share/', views.hospital_share, name='hospital_share'),
    path('hospital/<int:request_id>/location-sent/', views.mark_location_sent, name='mark_location_sent'),

    # Dashboards / profile
    path('dashboard/donor/', views.donor_dashboard, name='donor_dashboard'),
    path('dashboard/receiver/', views.receiver_dashboard, name='receiver_dashboard'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/donation/', views.donation_update, name='donation_update'),
    path('profile/history/', views.donation_history, name='donation_history'),
    path('profile/notification-settings/', views.notification_settings, name='notification_settings'),

    # Web push
    path('push/subscribe/', views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),

    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/mark-read/<int:notif_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),

    # Pages
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('report/<int:donor_id>/', views.report_abuse, name='report_abuse'),

    # Staff dashboard (protected)
    path('staff/dashboard/', views.admin_dashboard, name='admin_dashboard'),
]
