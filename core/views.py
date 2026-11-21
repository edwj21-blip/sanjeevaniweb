"""Views for Sanjeevani Blood Donor Platform."""
import json
import urllib.parse
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (
    DonorProfile, DonorContactRequest, HospitalLocationDetails,
    Notification, ContactMessage, AbuseReport, ActivityLog,
    KERALA_DISTRICTS, BLOOD_GROUPS
)
from .forms import (
    DonorRegistrationForm, DonorProfileEditForm, MobileLoginForm,
    ContactForm, HospitalLocationForm, DonorSearchForm
)


def log_activity(user, action, description='', request=None):
    """Helper to log user activity."""
    ip = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
    ActivityLog.objects.create(user=user, action=action, description=description, ip_address=ip)


def create_notification(user, title, message, notif_type='general', contact_request=None):
    """Helper to create a notification."""
    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notif_type,
        contact_request=contact_request,
    )


# ─────────────────────────── HOME ───────────────────────────

def home(request):
    """Homepage with statistics and donor highlights."""
    # Statistics from DB
    total_donors = DonorProfile.objects.filter(is_active=True, show_in_directory=True).count()
    available_donors = DonorProfile.objects.filter(is_active=True, show_in_directory=True, is_available=True).count()

    # Blood group counts
    blood_group_counts = {}
    for bg, label in BLOOD_GROUPS:
        count = DonorProfile.objects.filter(
            is_active=True, show_in_directory=True, blood_group=bg
        ).count()
        blood_group_counts[bg] = count

    # District counts
    district_counts = []
    for code, name in KERALA_DISTRICTS:
        count = DonorProfile.objects.filter(
            is_active=True, show_in_directory=True, district=code
        ).count()
        if count > 0:
            district_counts.append({'name': name, 'code': code, 'count': count})
    district_counts.sort(key=lambda x: x['count'], reverse=True)

    # Recent donors (for homepage preview)
    recent_donors = DonorProfile.objects.filter(
        is_active=True, show_in_directory=True
    ).select_related('user').order_by('-created_at')[:6]

    context = {
        'total_donors': total_donors,
        'available_donors': available_donors,
        'blood_group_counts': blood_group_counts,
        'district_counts': district_counts[:8],
        'recent_donors': recent_donors,
        'blood_groups': BLOOD_GROUPS,
        'districts': KERALA_DISTRICTS,
    }
    return render(request, 'home.html', context)


def set_language_view(request):
    """Set user language preference."""
    lang = request.POST.get('language', 'en')
    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/'))
    request.session['django_language'] = lang

    from django.utils import translation
    translation.activate(lang)
    response = redirect(next_url)
    response.set_cookie('django_language', lang)
    from django.conf import settings
    response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang)
    return response


# ─────────────────────────── AUTH ───────────────────────────

def donor_register(request):
    """Donor registration view."""
    if request.user.is_authenticated:
        try:
            profile = request.user.donor_profile
            return redirect('core:donor_dashboard')
        except DonorProfile.DoesNotExist:
            pass

    form = DonorRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            # Create user
            first_name = data['full_name'].split(' ')[0]
            last_name = ' '.join(data['full_name'].split(' ')[1:])
            user = User.objects.create_user(
                username=data['mobile'],
                password=data['password'],
                first_name=first_name,
                last_name=last_name,
                email=data.get('email', ''),
            )
            # Create donor profile
            profile = DonorProfile.objects.create(
                user=user,
                mobile=data['mobile'],
                blood_group=data['blood_group'],
                district=data['district'],
                locality=data['locality'],
                last_donation_date=data.get('last_donation_date'),
                is_available=data.get('is_available', True),
                show_in_directory=data.get('show_in_directory', True),
                share_contact=data.get('share_contact', True),
                show_last_donation_date=data.get('show_last_donation_date', False),
            )
            # Log activity
            log_activity(user, 'donor_registered', f"New donor: {user.get_full_name()}", request)

        # Auto-login
        login(request, user)
        messages.success(request, _('Registration successful! Welcome to Sanjeevani.'))
        return redirect('core:donor_dashboard')

    return render(request, 'auth/register.html', {'form': form})


def donor_login(request):
    """Login with mobile number."""
    if request.user.is_authenticated:
        return redirect('core:home')

    form = MobileLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        mobile = form.cleaned_data['mobile']
        password = form.cleaned_data['password']
        user = authenticate(request, username=mobile, password=password)
        if user:
            login(request, user)
            log_activity(user, 'login', '', request)
            next_url = request.GET.get('next', '')
            if next_url:
                return redirect(next_url)
            try:
                user.donor_profile
                return redirect('core:donor_dashboard')
            except DonorProfile.DoesNotExist:
                return redirect('core:home')
        else:
            messages.error(request, _('Invalid mobile number or password.'))

    return render(request, 'auth/login.html', {'form': form})


def donor_logout(request):
    """Logout view."""
    if request.user.is_authenticated:
        log_activity(request.user, 'logout', '', request)
    logout(request)
    messages.info(request, _('You have been logged out.'))
    return redirect('core:home')


# ─────────────────────────── DONOR DIRECTORY ───────────────────────────

def donor_directory(request):
    """Searchable donor directory."""
    form = DonorSearchForm(request.GET or None)
    donors = DonorProfile.objects.filter(
        is_active=True, show_in_directory=True
    ).select_related('user').order_by('-is_available', '-created_at')

    if form.is_valid():
        bg = form.cleaned_data.get('blood_group')
        district = form.cleaned_data.get('district')
        locality = form.cleaned_data.get('locality')
        available_only = form.cleaned_data.get('available_only')

        if bg:
            donors = donors.filter(blood_group=bg)
        if district:
            donors = donors.filter(district=district)
        if locality:
            donors = donors.filter(locality__icontains=locality)
        if available_only:
            donors = donors.filter(is_available=True)

    paginator = Paginator(donors, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'form': form,
        'page_obj': page_obj,
        'total_results': donors.count(),
        'blood_groups': BLOOD_GROUPS,
        'districts': KERALA_DISTRICTS,
    }
    return render(request, 'donors/directory.html', context)


def donor_detail(request, donor_id):
    """Individual donor detail page."""
    donor = get_object_or_404(DonorProfile, id=donor_id, is_active=True, show_in_directory=True)
    return render(request, 'donors/detail.html', {'donor': donor})


# ─────────────────────────── CONTACT & CONFIRMATION FLOW ───────────────────────────

@login_required
def initiate_contact(request, donor_id):
    """Step 1: Receiver initiates contact with donor."""
    donor = get_object_or_404(DonorProfile, id=donor_id, is_active=True)

    # Check receiver is not trying to contact themselves
    if hasattr(request.user, 'donor_profile') and request.user.donor_profile == donor:
        messages.error(request, _('You cannot contact yourself.'))
        return redirect('core:donor_directory')

    # Create or get existing open request
    contact_request, created = DonorContactRequest.objects.get_or_create(
        receiver=request.user,
        donor_profile=donor,
        status='initiated',
        defaults={'status': 'initiated'}
    )

    if created:
        log_activity(request.user, 'contact_initiated', f"Contacted donor {donor.id}", request)
        # Notify donor
        create_notification(
            donor.user,
            'New Contact Request',
            f'Someone is trying to reach you for blood donation. Please check your dashboard.',
            'call_initiated',
            contact_request,
        )

    return render(request, 'donors/contact.html', {
        'donor': donor,
        'contact_request': contact_request,
    })


@login_required
@require_POST
def receiver_confirm_call(request, request_id):
    """Step 2: Receiver confirms they spoke to the donor."""
    contact_request = get_object_or_404(
        DonorContactRequest, id=request_id, receiver=request.user
    )
    if not contact_request.receiver_confirmed_call:
        contact_request.receiver_confirmed_call = True
        contact_request.receiver_confirmed_at = timezone.now()
        contact_request.status = 'receiver_confirmed'
        contact_request.save()

        log_activity(request.user, 'receiver_confirmed_call', f"Request {request_id}", request)
        # Notify donor
        create_notification(
            contact_request.donor_profile.user,
            'Receiver Confirmed Call',
            'The person looking for blood has confirmed speaking with you. Please respond from your dashboard.',
            'call_confirmed',
            contact_request,
        )

    return JsonResponse({'success': True, 'status': contact_request.status})


@login_required
def donor_respond(request, request_id, action):
    """Step 3: Donor confirms or declines."""
    try:
        donor_profile = request.user.donor_profile
    except DonorProfile.DoesNotExist:
        messages.error(request, _('You are not registered as a donor.'))
        return redirect('core:home')

    contact_request = get_object_or_404(
        DonorContactRequest, id=request_id, donor_profile=donor_profile
    )

    if contact_request.donor_responded:
        messages.info(request, _('You have already responded to this request.'))
        return redirect('core:donor_dashboard')

    if action == 'confirm':
        contact_request.status = 'donor_confirmed'
        contact_request.donor_responded = True
        contact_request.donor_response_at = timezone.now()
        contact_request.save()

        log_activity(request.user, 'donor_confirmed', f"Request {request_id}", request)
        create_notification(
            contact_request.receiver,
            'Donor Confirmed!',
            f'Great news! The donor has confirmed willingness to donate blood.',
            'donor_confirmed',
            contact_request,
        )
        messages.success(request, _('Thank you! You confirmed your willingness to donate.'))

    elif action == 'decline':
        contact_request.status = 'donor_declined'
        contact_request.donor_responded = True
        contact_request.donor_response_at = timezone.now()
        contact_request.save()

        log_activity(request.user, 'donor_declined', f"Request {request_id}", request)
        create_notification(
            contact_request.receiver,
            'Donor Unavailable',
            'The donor is currently unable to donate. Please search for another donor.',
            'donor_declined',
            contact_request,
        )
        messages.info(request, _('Response saved. Thank you for letting us know.'))

    return redirect('core:donor_dashboard')


@login_required
def check_status(request, request_id):
    """AJAX endpoint to poll contact request status."""
    contact_request = get_object_or_404(
        DonorContactRequest, id=request_id
    )
    # Only allow receiver or donor to check
    is_receiver = contact_request.receiver == request.user
    is_donor = hasattr(request.user, 'donor_profile') and contact_request.donor_profile == request.user.donor_profile
    if not (is_receiver or is_donor):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # Mark notification as read if checking
    unread = Notification.objects.filter(
        user=request.user, contact_request=contact_request, is_read=False
    )
    unread.update(is_read=True)

    return JsonResponse({
        'status': contact_request.status,
        'receiver_confirmed': contact_request.receiver_confirmed_call,
        'donor_responded': contact_request.donor_responded,
        'whatsapp_opened': contact_request.whatsapp_opened,
        'location_sent': contact_request.location_whatsapp_opened,
    })


@login_required
def whatsapp_confirmation(request, request_id):
    """Generate WhatsApp confirmation URL and mark as opened."""
    contact_request = get_object_or_404(
        DonorContactRequest, id=request_id, receiver=request.user
    )
    if contact_request.status != 'donor_confirmed':
        messages.error(request, _('WhatsApp confirmation is only available after donor confirms.'))
        return redirect('core:receiver_dashboard')

    donor = contact_request.donor_profile
    if not donor.share_contact:
        messages.error(request, _('The donor has not consented to share contact details.'))
        return redirect('core:receiver_dashboard')

    wa_number = donor.get_whatsapp_number()
    wa_message = (
        f"Hello, this is regarding our blood donation conversation through Sanjeevani. "
        f"Thank you for confirming your willingness to donate blood. "
        f"I would like to coordinate the next steps with you."
    )
    wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(wa_message)}"

    # Mark opened
    if not contact_request.whatsapp_opened:
        contact_request.whatsapp_opened = True
        contact_request.whatsapp_opened_at = timezone.now()
        contact_request.status = 'whatsapp_sent'
        contact_request.save()
        log_activity(request.user, 'whatsapp_confirmation_opened', f"Request {request_id}", request)

    return render(request, 'donors/whatsapp_confirm.html', {
        'contact_request': contact_request,
        'donor': donor,
        'wa_url': wa_url,
    })


@login_required
def hospital_location(request, request_id):
    """Step: Receiver shares hospital location."""
    contact_request = get_object_or_404(
        DonorContactRequest, id=request_id, receiver=request.user
    )

    # Must have opened WhatsApp first
    if not contact_request.whatsapp_opened:
        messages.error(request, _('Please send the WhatsApp confirmation first.'))
        return redirect('core:whatsapp_confirmation', request_id=request_id)

    donor = contact_request.donor_profile

    # Check if location already saved
    try:
        location = contact_request.hospital_location
    except HospitalLocationDetails.DoesNotExist:
        location = None

    form = HospitalLocationForm(request.POST or None, instance=location)

    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            loc = form.save(commit=False)
            loc.contact_request = contact_request
            loc.save()

        # Prepare WhatsApp message
        wa_number = donor.get_whatsapp_number()
        wa_message = (
            f"Hello, here is the hospital location for the blood donation.\n\n"
            f"Hospital: {loc.hospital_name}\n\n"
            f"Address: {loc.full_address}\n\n"
            f"Google Maps: {loc.google_maps_link}\n\n"
            f"Please check the location details."
        )
        wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(wa_message)}"

        return render(request, 'donors/hospital_location_preview.html', {
            'contact_request': contact_request,
            'donor': donor,
            'location': loc,
            'wa_url': wa_url,
        })

    return render(request, 'donors/hospital_location.html', {
        'contact_request': contact_request,
        'donor': donor,
        'form': form,
        'location': location,
        'districts': KERALA_DISTRICTS,
    })


@login_required
@require_POST
def mark_whatsapp_sent(request, request_id):
    contact_request = get_object_or_404(DonorContactRequest, id=request_id, receiver=request.user)
    contact_request.whatsapp_opened = True
    contact_request.whatsapp_opened_at = timezone.now()
    if contact_request.status == 'donor_confirmed':
        contact_request.status = 'whatsapp_sent'
    contact_request.save()
    return JsonResponse({'success': True})


@login_required
@require_POST
def mark_location_sent(request, request_id):
    contact_request = get_object_or_404(DonorContactRequest, id=request_id, receiver=request.user)
    contact_request.location_whatsapp_opened = True
    contact_request.location_whatsapp_opened_at = timezone.now()
    contact_request.status = 'location_sent'
    contact_request.save()
    log_activity(request.user, 'location_whatsapp_opened', f"Request {request_id}", request)
    return JsonResponse({'success': True})


# ─────────────────────────── DASHBOARDS ───────────────────────────

@login_required
def donor_dashboard(request):
    """Dashboard for registered donors."""
    try:
        profile = request.user.donor_profile
    except DonorProfile.DoesNotExist:
        messages.info(request, _('Please register as a donor to access the donor dashboard.'))
        return redirect('core:register')

    # Pending contact requests (receiver confirmed, donor not responded)
    pending_requests = DonorContactRequest.objects.filter(
        donor_profile=profile,
        receiver_confirmed_call=True,
        donor_responded=False,
    ).select_related('receiver').order_by('-created_at')

    # Recent contact history
    recent_contacts = DonorContactRequest.objects.filter(
        donor_profile=profile,
    ).select_related('receiver').order_by('-created_at')[:10]

    # Notifications
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')[:10]

    unread_notifs = Notification.objects.filter(user=request.user, is_read=False).count()

    context = {
        'profile': profile,
        'pending_requests': pending_requests,
        'recent_contacts': recent_contacts,
        'notifications': notifications,
        'unread_notifs': unread_notifs,
        'districts': dict(KERALA_DISTRICTS),
    }
    return render(request, 'dashboard/donor.html', context)


@login_required
def receiver_dashboard(request):
    """Dashboard for receivers (people looking for blood)."""
    my_requests = DonorContactRequest.objects.filter(
        receiver=request.user
    ).select_related('donor_profile', 'donor_profile__user').order_by('-created_at')

    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')[:10]

    unread_notifs = Notification.objects.filter(user=request.user, is_read=False).count()

    context = {
        'my_requests': my_requests,
        'notifications': notifications,
        'unread_notifs': unread_notifs,
    }
    return render(request, 'dashboard/receiver.html', context)


@login_required
def edit_profile(request):
    """Edit donor profile."""
    try:
        profile = request.user.donor_profile
    except DonorProfile.DoesNotExist:
        messages.error(request, _('No donor profile found.'))
        return redirect('core:home')

    form = DonorProfileEditForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        profile = form.save(commit=False)
        # Update user name
        full_name = form.cleaned_data.get('full_name', '')
        if full_name:
            parts = full_name.split(' ', 1)
            request.user.first_name = parts[0]
            request.user.last_name = parts[1] if len(parts) > 1 else ''
            request.user.save()
        profile.save()
        messages.success(request, _('Profile updated successfully.'))
        return redirect('core:donor_dashboard')

    return render(request, 'dashboard/edit_profile.html', {'form': form, 'profile': profile})


# ─────────────────────────── NOTIFICATIONS ───────────────────────────

@login_required
def notifications(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'notifications.html', {'notifications': notifs})


@login_required
def mark_notification_read(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    notif.is_read = True
    notif.save()
    return JsonResponse({'success': True})


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


# ─────────────────────────── STATIC PAGES ───────────────────────────

def about(request):
    return render(request, 'pages/about.html')


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, _('Thank you for your message. We will get back to you soon.'))
        return redirect('core:contact')
    return render(request, 'pages/contact.html', {'form': form})


def privacy(request):
    return render(request, 'pages/privacy.html')


def terms(request):
    return render(request, 'pages/terms.html')


@login_required
@require_POST
def report_abuse(request, donor_id):
    donor = get_object_or_404(DonorProfile, id=donor_id)
    reason = request.POST.get('reason', '')
    if reason:
        AbuseReport.objects.create(reporter=request.user, reported_donor=donor, reason=reason)
        messages.success(request, _('Report submitted. Our team will review it.'))
    return redirect('core:donor_directory')


# ─────────────────────────── ERROR HANDLERS ───────────────────────────

def custom_404(request, exception):
    return render(request, 'errors/404.html', status=404)


def custom_500(request):
    return render(request, 'errors/500.html', status=500)
