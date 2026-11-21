"""URL configuration for core app."""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    path('set-language/', views.set_language_view, name='set_language'),

    # Authentication
    path('register/', views.donor_register, name='register'),
    path('login/', views.donor_login, name='login'),
    path('logout/', views.donor_logout, name='logout'),

    # Donor Directory
    path('donors/', views.donor_directory, name='donor_directory'),
    path('donors/<int:donor_id>/', views.donor_detail, name='donor_detail'),

    # Contact & Confirmation Flow
    path('contact/<int:donor_id>/', views.initiate_contact, name='initiate_contact'),
    path('confirm-call/<int:request_id>/', views.receiver_confirm_call, name='receiver_confirm_call'),
    path('donor-respond/<int:request_id>/<str:action>/', views.donor_respond, name='donor_respond'),
    path('check-status/<int:request_id>/', views.check_status, name='check_status'),
    path('whatsapp-confirmation/<int:request_id>/', views.whatsapp_confirmation, name='whatsapp_confirmation'),
    path('hospital-location/<int:request_id>/', views.hospital_location, name='hospital_location'),
    path('mark-whatsapp-sent/<int:request_id>/', views.mark_whatsapp_sent, name='mark_whatsapp_sent'),
    path('mark-location-sent/<int:request_id>/', views.mark_location_sent, name='mark_location_sent'),

    # Dashboards
    path('dashboard/donor/', views.donor_dashboard, name='donor_dashboard'),
    path('dashboard/receiver/', views.receiver_dashboard, name='receiver_dashboard'),

    # Profile
    path('profile/edit/', views.edit_profile, name='edit_profile'),

    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/mark-read/<int:notif_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),

    # Pages
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),

    # Abuse Report
    path('report/<int:donor_id>/', views.report_abuse, name='report_abuse'),
]
