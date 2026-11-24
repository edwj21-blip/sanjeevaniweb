"""Views for Sanjeevani Blood Donor Platform."""
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.views.decorators.http import require_GET, require_POST

from . import eligibility
from .forms import (
    ContactForm, DonationUpdateForm, DonorProfileEditForm, DonorRegistrationForm,
    DonorSearchForm, MobileLoginForm, NotificationSettingsForm, ReceiverSignupForm,
)
from .models import (
    BLOOD_GROUPS, KERALA_DISTRICTS, AbuseReport, ActivityLog, ContactMessage,
    DonationRecord, DonorContactRequest, DonorProfile, EligibilitySettings,
    HospitalLocationDetails, Notification, PushSubscription, Reminder,
)
from .services import (
    build_navigation_url, build_whatsapp_url, create_notification, log_activity,
    push_configured, record_donation, recalc_donor, refresh_due_donors, today,
)
from .translations import tr

OPEN_STATUSES = ('initiated', 'receiver_confirmed', 'donor_confirmed', 'hospital_selected')
CALL_PENDING_MINUTES = 30


def get_donor(user):
    try:
        return user.donor_profile
    except DonorProfile.DoesNotExist:
        return None


def json_error(message, status=400):
    return JsonResponse({'ok': False, 'error': message}, status=status)


# ─────────────────────────── HOME ───────────────────────────
def home(request):
    refresh_due_donors()
    searchable = DonorProfile.objects.searchable()
    ctx = {
        'blood_groups': [b for b, _ in BLOOD_GROUPS],
        'stat_total': searchable.count(),
        'stat_available': searchable.filter(is_available=True).count(),
        'stat_unavailable': searchable.filter(is_available=False).count(),
        'stat_districts': searchable.order_by().values('district').distinct().count(),
        'recent_donors': searchable.select_related('user').order_by('-created_at')[:6],
        'districts': KERALA_DISTRICTS,
        'district_counts': dict(searchable.order_by().values_list('district').annotate(n=Count('id'))),
    }
    return render(request, 'home.html', ctx)


def set_language_view(request):
    lang = request.POST.get('language', 'en')
    if lang not in dict(settings.LANGUAGES):
        lang = 'en'
    next_url = request.POST.get('next') or '/'
    if not next_url.startswith('/'):
        next_url = '/'
    translation.activate(lang)
    response = redirect(next_url)
    response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang, max_age=365 * 86400, samesite='Lax')
    return response


# ─────────────────────────── AUTH ───────────────────────────
@transaction.atomic
def donor_register(request):
    """One-time donor registration with mandatory server-side 18+ check."""
    if request.user.is_authenticated and get_donor(request.user):
        return redirect('core:donor_dashboard')

    form = DonorRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        parts = d['full_name'].strip().split(' ', 1)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=d['mobile'], password=d['password'], email=d.get('email', ''),
                    first_name=parts[0], last_name=parts[1] if len(parts) > 1 else '',
                )
                donor = DonorProfile.objects.create(
                    user=user, mobile=d['mobile'], date_of_birth=d['date_of_birth'],
                    blood_group=d['blood_group'], district=d['district'], locality=d['locality'],
                    share_contact=True, health_declaration=d['health_declaration'],
                    show_in_directory=d['show_in_directory'],
                    show_last_donation_date=d['show_last_donation_date'],
                )
                if d.get('last_donation_date'):
                    record_donation(donor, d['last_donation_date'],
                                    d.get('last_donation_type') or 'whole_blood', source='registration')
                else:
                    recalc_donor(donor)
        except IntegrityError:
            form.add_error('mobile', tr('This mobile number is already registered.'))
        else:
            login(request, user)
            log_activity(user, 'register', 'Donor registered', request)
            messages.success(request, tr('Registration successful. Welcome to Sanjeevani!'))
            return redirect('core:donor_dashboard')

    return render(request, 'auth/register.html', {
        'form': form, 'adult_cutoff': eligibility.adult_cutoff(today()).isoformat(),
        'today': today().isoformat(),
    })


def receiver_signup(request):
    """Light account for people who need blood but are not donors."""
    if request.user.is_authenticated:
        return redirect('core:home')
    form = ReceiverSignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        parts = d['full_name'].strip().split(' ', 1)
        user = User.objects.create_user(
            username=d['mobile'], password=d['password'],
            first_name=parts[0], last_name=parts[1] if len(parts) > 1 else '',
        )
        login(request, user)
        messages.success(request, tr('Account created. You can now search for donors.'))
        return redirect('core:donor_directory')
    return render(request, 'auth/signup.html', {'form': form})


def _safe_next(request):
    nxt = request.GET.get('next') or request.POST.get('next') or ''
    return nxt if nxt.startswith('/') and not nxt.startswith('//') else ''


def donor_login(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    form = MobileLoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(request, username=form.cleaned_data['mobile'], password=form.cleaned_data['password'])
        if user:
            login(request, user)
            log_activity(user, 'login', '', request)
            nxt = _safe_next(request)
            if nxt:
                return redirect(nxt)
            return redirect('core:donor_dashboard' if get_donor(user) else 'core:donor_directory')
        messages.error(request, tr('Invalid mobile number or password.'))
    return render(request, 'auth/login.html', {'form': form, 'next': _safe_next(request)})


def donor_logout(request):
    if request.user.is_authenticated:
        log_activity(request.user, 'logout', '', request)
    logout(request)
    messages.info(request, tr('You have been logged out.'))
    return redirect('core:home')


# ─────────────────────────── FIND BLOOD ───────────────────────────
def donor_directory(request):
    """Public search. Available AND unavailable donors are always listed."""
    refresh_due_donors()
    form = DonorSearchForm(request.GET or None)
    donors = DonorProfile.objects.searchable().select_related('user')
    if form.is_valid():
        c = form.cleaned_data
        if c['blood_group']:
            donors = donors.filter(blood_group=c['blood_group'])
        if c['district']:
            donors = donors.filter(district=c['district'])
        if c['locality']:
            donors = donors.filter(locality__icontains=c['locality'])
        if c['name']:
            q = c['name']
            donors = donors.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q))
        if c['availability'] == 'available':
            donors = donors.filter(is_available=True)
        elif c['availability'] == 'unavailable':
            donors = donors.filter(is_available=False)
    donors = donors.order_by('-is_available', 'user__first_name', 'id')
    page = Paginator(donors, 12).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'donors/directory.html', {
        'form': form, 'page': page, 'total': page.paginator.count,
        'querystring': params.urlencode(),
    })


def donor_detail(request, donor_id):
    return redirect('core:donor_directory')


# ─────────────── CALL → CONFIRM → DONOR POPUP → RECEIVER POPUP (JSON) ───────────────
@login_required
@require_POST
def api_call_start(request, donor_id):
    """Receiver pressed Call Now. Returns the tel: URI; nothing is dialled by the server."""
    donor = get_object_or_404(DonorProfile.objects.searchable(), id=donor_id)
    refresh_due_donors()
    donor.refresh_from_db()
    if donor.user_id == request.user.id:
        return json_error(tr('You cannot call yourself.'), 400)
    if not donor.is_available:
        return json_error(tr('This donor is currently unavailable.'), 409)
    if not donor.share_contact:
        return json_error(tr('This donor has not agreed to be contacted.'), 403)

    existing = DonorContactRequest.objects.filter(
        receiver=request.user, donor_profile=donor, status__in=OPEN_STATUSES).first()
    if existing and existing.status != 'initiated':
        return JsonResponse({'ok': True, 'duplicate': True, 'status': existing.status,
                             'request_id': existing.id, 'tel': f'tel:+91{donor.mobile}'})
    since = timezone.now() - timedelta(hours=24)
    if DonorContactRequest.objects.filter(receiver=request.user, created_at__gte=since).count() >= 20:
        return json_error(tr('Too many requests today. Please try again later.'), 429)

    req = existing or DonorContactRequest.objects.create(receiver=request.user, donor_profile=donor)
    if existing:
        DonorContactRequest.objects.filter(pk=existing.pk).update(created_at=timezone.now())
    log_activity(request.user, 'call_start', f'donor={donor.id}', request)
    return JsonResponse({'ok': True, 'duplicate': False, 'status': req.status,
                         'request_id': req.id, 'tel': f'tel:+91{donor.mobile}'})


@login_required
@require_POST
def api_call_confirm(request, request_id):
    """Receiver answers 'Did you successfully connect with the donor?'"""
    req = get_object_or_404(DonorContactRequest, id=request_id, receiver=request.user)
    connected = request.POST.get('connected') == 'yes'
    if connected:
        updated = DonorContactRequest.objects.filter(pk=req.pk, status='initiated').update(
            status='receiver_confirmed', receiver_confirmed_call=True,
            receiver_confirmed_at=timezone.now())
        if updated:   # only the first confirmation notifies the donor
            create_notification(
                req.donor_profile.user, tr('Blood Donation Request'),
                tr('Someone has contacted you regarding blood donation. Are you willing to donate?'),
                'donor_request', req)
        return JsonResponse({'ok': True, 'status': 'receiver_confirmed', 'duplicate': not updated})
    DonorContactRequest.objects.filter(pk=req.pk, status='initiated').update(status='not_connected')
    return JsonResponse({'ok': True, 'status': 'not_connected'})


@login_required
@require_POST
def api_respond(request, request_id):
    """Donor accepts or declines inside the website. Only one response is ever stored."""
    donor = get_donor(request.user)
    req = get_object_or_404(DonorContactRequest, id=request_id, donor_profile=donor) if donor else None
    if not req:
        return json_error('Forbidden', 403)
    action = request.POST.get('action')
    if action not in ('accept', 'decline'):
        return json_error('Invalid action')
    if action == 'accept' and not donor.is_available:
        return json_error(tr('You are currently unavailable, so you cannot accept this request.'), 409)

    new_status = 'donor_confirmed' if action == 'accept' else 'donor_declined'
    updated = DonorContactRequest.objects.filter(
        pk=req.pk, status='receiver_confirmed', donor_responded=False,
    ).update(status=new_status, donor_responded=True, donor_response_at=timezone.now())
    if not updated:
        return json_error(tr('This request has already been answered.'), 409)

    if action == 'accept':
        create_notification(req.receiver, tr('Donor confirmed'),
                            tr('The donor is willing to donate blood. Your request has been confirmed.'),
                            'donor_confirmed', req)
    else:
        create_notification(req.receiver, tr('Donor unavailable'),
                            tr('Sorry, this donor is currently unavailable.'), 'donor_declined', req)
    return JsonResponse({'ok': True, 'status': new_status})


@login_required
@require_POST
def api_ack(request, request_id):
    req = get_object_or_404(DonorContactRequest, id=request_id, receiver=request.user)
    DonorContactRequest.objects.filter(pk=req.pk).update(receiver_ack=True)
    return JsonResponse({'ok': True})


@login_required
@require_GET
def api_poll(request):
    """Polled by the page every few seconds; everything comes from the database."""
    now = timezone.now()
    DonorContactRequest.objects.filter(
        status='initiated', created_at__lt=now - timedelta(minutes=CALL_PENDING_MINUTES),
    ).update(status='expired')
    # a request the donor never answered for 3 days is closed
    DonorContactRequest.objects.filter(
        status='receiver_confirmed', donor_responded=False, created_at__lt=now - timedelta(days=3),
    ).update(status='expired')

    data = {
        'unread': Notification.objects.filter(user=request.user, is_read=False).count(),
        'donor_requests': [], 'receiver_updates': [], 'call_pending': None,
    }
    donor = get_donor(request.user)
    if donor:
        for r in DonorContactRequest.objects.filter(
                donor_profile=donor, status='receiver_confirmed', donor_responded=False
        ).order_by('created_at'):
            data['donor_requests'].append({'id': r.id, 'can_accept': donor.is_available})

    for r in DonorContactRequest.objects.filter(
            receiver=request.user, status__in=('donor_confirmed', 'donor_declined'), receiver_ack=False
    ).select_related('donor_profile__user').order_by('created_at'):
        item = {'id': r.id, 'status': r.status}
        if r.status == 'donor_confirmed':
            dp = r.donor_profile
            item.update(name=dp.get_display_name(), blood_group=dp.blood_group,
                        locality=dp.locality, district=dp.get_district_display(),
                        mobile=dp.mobile, hospital_url=f'/hospital/{r.id}/')
        data['receiver_updates'].append(item)

    pending = DonorContactRequest.objects.filter(
        receiver=request.user, status='initiated',
        created_at__gte=now - timedelta(minutes=CALL_PENDING_MINUTES),
    ).select_related('donor_profile__user').order_by('-created_at').first()
    if pending:
        data['call_pending'] = {'id': pending.id, 'name': pending.donor_profile.get_display_name()}
    return JsonResponse(data)


# ─────────────────────────── HOSPITAL (GOOGLE MAPS) ───────────────────────────
def _receiver_request(request, request_id, statuses):
    req = get_object_or_404(DonorContactRequest, id=request_id, receiver=request.user)
    if req.status not in statuses:
        return req, False
    return req, True


@login_required
def hospital_select(request, request_id):
    req, ok = _receiver_request(request, request_id, ('donor_confirmed', 'hospital_selected', 'location_sent'))
    if not ok:
        messages.warning(request, tr('The donor has not confirmed this request yet.'))
        return redirect('core:receiver_dashboard')
    hospital = getattr(req, 'hospital_location', None)
    return render(request, 'donors/hospital_select.html', {
        'req': req, 'hospital': hospital,
        'maps_key': settings.GOOGLE_MAPS_API_KEY,
    })


@login_required
@require_POST
def api_hospital_save(request, request_id):
    req, ok = _receiver_request(request, request_id, ('donor_confirmed', 'hospital_selected', 'location_sent'))
    if not ok:
        return json_error('Forbidden', 403)
    try:
        body = json.loads(request.body.decode('utf-8'))
        name = str(body.get('name', '')).strip()[:200]
        address = str(body.get('address', '')).strip()[:1000]
        place_id = str(body.get('place_id', '')).strip()[:300]
        lat = Decimal(str(body.get('lat'))).quantize(Decimal('0.000001'))
        lng = Decimal(str(body.get('lng'))).quantize(Decimal('0.000001'))
    except (ValueError, InvalidOperation, TypeError):
        return json_error(tr('Invalid hospital details.'))
    if not name or not address or not (Decimal(-90) <= lat <= Decimal(90)) or not (Decimal(-180) <= lng <= Decimal(180)):
        return json_error(tr('Please provide the hospital name, address and a valid location.'))

    url = build_navigation_url(lat, lng, place_id)
    HospitalLocationDetails.objects.update_or_create(
        contact_request=req,
        defaults=dict(hospital_name=name, full_address=address, latitude=lat, longitude=lng,
                      place_id=place_id, google_maps_link=url, district=req.donor_profile.district),
    )
    if req.status == 'donor_confirmed':
        DonorContactRequest.objects.filter(pk=req.pk, status='donor_confirmed').update(
            status='hospital_selected', receiver_ack=True)
    return JsonResponse({'ok': True, 'redirect': f'/hospital/{req.id}/share/'})


@login_required
def hospital_share(request, request_id):
    req, ok = _receiver_request(request, request_id, ('hospital_selected', 'location_sent'))
    hospital = getattr(req, 'hospital_location', None) if ok else None
    if not hospital:
        return redirect('core:hospital_select', request_id=req.id)
    return render(request, 'donors/hospital_share.html', {
        'req': req, 'hospital': hospital,
        'whatsapp_url': build_whatsapp_url(req.donor_profile.mobile, hospital),
    })


@login_required
@require_POST
def mark_location_sent(request, request_id):
    """Called when the receiver opens WhatsApp Click-to-Chat (they still press Send)."""
    req = get_object_or_404(DonorContactRequest, id=request_id, receiver=request.user)
    if req.status == 'hospital_selected':
        DonorContactRequest.objects.filter(pk=req.pk, status='hospital_selected').update(
            status='location_sent', location_whatsapp_opened=True, location_whatsapp_opened_at=timezone.now())
        create_notification(req.donor_profile.user, tr('Hospital location shared'),
                            tr('The receiver has shared the hospital location with you on WhatsApp.'),
                            'location_shared', req)
    return JsonResponse({'ok': True})


# ─────────────────────────── DONOR PROFILE ───────────────────────────
@login_required
def donor_dashboard(request):
    donor = get_donor(request.user)
    if not donor:
        return redirect('core:receiver_dashboard')
    refresh_due_donors()
    donor.refresh_from_db()
    return render(request, 'dashboard/donor.html', {
        'donor': donor,
        'history': donor.donations.filter(status='completed')[:5],
        'cfg': EligibilitySettings.load(),
        'needs_dob': donor.date_of_birth is None,
        'next_reminder': donor.reminders.filter(status='pending').first(),
    })


@login_required
def donation_update(request):
    donor = get_donor(request.user)
    if not donor:
        return redirect('core:register')
    if not donor.date_of_birth:
        messages.warning(request, tr('Please add your date of birth first.'))
        return redirect('core:edit_profile')
    form = DonationUpdateForm(request.POST or None, donor=donor)
    if request.method == 'POST' and form.is_valid():
        try:
            record_donation(donor, form.cleaned_data['donation_date'], form.cleaned_data['donation_type'])
        except IntegrityError:
            form.add_error('donation_date', tr('A donation is already recorded for this date.'))
        else:
            donor.refresh_from_db()
            messages.success(request, tr('Donation saved. Your status is now Unavailable until your next eligible date.'))
            return redirect('core:donor_dashboard')
    return render(request, 'dashboard/donation_update.html', {'form': form, 'donor': donor, 'today': today().isoformat()})


@login_required
def donation_history(request):
    donor = get_donor(request.user)
    if not donor:
        return redirect('core:register')
    return render(request, 'dashboard/donation_history.html', {
        'donor': donor, 'records': donor.donations.filter(status='completed')})


@login_required
def edit_profile(request):
    donor = get_donor(request.user)
    if not donor:
        return redirect('core:register')
    form = DonorProfileEditForm(request.POST or None, instance=donor)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            obj = form.save()
            name = form.cleaned_data['full_name'].strip().split(' ', 1)
            request.user.first_name = name[0]
            request.user.last_name = name[1] if len(name) > 1 else ''
            request.user.save()
            recalc_donor(obj)
        messages.success(request, tr('Profile updated successfully.'))
        return redirect('core:donor_dashboard')
    return render(request, 'dashboard/edit_profile.html', {
        'form': form, 'donor': donor, 'adult_cutoff': eligibility.adult_cutoff(today()).isoformat(),
        'today': today().isoformat()})


@login_required
def notification_settings(request):
    donor = get_donor(request.user)
    if not donor:
        return redirect('core:register')
    form = NotificationSettingsForm(request.POST or None, instance=donor)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, tr('Notification settings saved.'))
        return redirect('core:notification_settings')
    return render(request, 'dashboard/notification_settings.html', {
        'form': form, 'donor': donor,
        'push_ready': push_configured(), 'vapid_public_key': settings.VAPID_PUBLIC_KEY,
        'subscriptions': request.user.push_subscriptions.filter(is_active=True).count(),
        'next_reminder': donor.reminders.filter(status='pending').first(),
    })


@login_required
@require_POST
def push_subscribe(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        endpoint = body['endpoint']
        keys = body['keys']
        p256dh, auth = keys['p256dh'], keys['auth']
    except (ValueError, KeyError, TypeError):
        return json_error('Invalid subscription')
    if not str(endpoint).startswith('https://') or len(endpoint) > 700:
        return json_error('Invalid endpoint')
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults=dict(user=request.user, p256dh=p256dh[:255], auth=auth[:255], is_active=True,
                      failure_count=0, user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]),
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        endpoint = json.loads(request.body.decode('utf-8')).get('endpoint', '')
    except ValueError:
        return json_error('Invalid request')
    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({'ok': True})


def service_worker(request):
    resp = HttpResponse(render_to_string('sw.js'), content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    resp['Cache-Control'] = 'no-cache'
    return resp


@login_required
def receiver_dashboard(request):
    reqs = (DonorContactRequest.objects.filter(receiver=request.user)
            .select_related('donor_profile__user').order_by('-created_at')[:50])
    return render(request, 'dashboard/receiver.html', {'requests': reqs})


@login_required
def notifications(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')[:100]
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'notifications.html', {'notifications': notifs})


@login_required
@require_POST
def mark_notification_read(request, notif_id):
    Notification.objects.filter(id=notif_id, user=request.user).update(is_read=True)
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
        messages.success(request, tr('Thank you for your message. We will get back to you soon.'))
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
    reason = request.POST.get('reason', '').strip()
    if reason:
        AbuseReport.objects.create(reporter=request.user, reported_donor=donor, reason=reason)
        messages.success(request, tr('Report submitted. Our team will review it.'))
    return redirect('core:donor_directory')


# ─────────────────────────── STAFF DASHBOARD ───────────────────────────
@staff_member_required
def admin_dashboard(request):
    refresh_due_donors()
    donors = DonorProfile.objects.all()
    q = request.GET.get('q', '').strip()
    found = None
    if q:
        found = donors.filter(
            Q(mobile__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
            | Q(locality__icontains=q)).select_related('user')[:50]

    blood_stats = (donors.values('blood_group').annotate(
        total=Count('id'), available=Count('id', filter=Q(is_available=True))).order_by('blood_group'))
    district_stats = (donors.values('district').annotate(
        total=Count('id'), available=Count('id', filter=Q(is_available=True))).order_by('district'))
    dup_groups = (donors.exclude(date_of_birth=None).values('user__first_name', 'user__last_name', 'date_of_birth')
                  .order_by().annotate(n=Count('id')).filter(n__gt=1))
    cfg = EligibilitySettings.load()
    return render(request, 'dashboard/admin_dashboard.html', {
        'total': donors.count(),
        'available': donors.filter(is_available=True).count(),
        'unavailable': donors.filter(is_available=False).count(),
        'missing_dob': donors.filter(date_of_birth__isnull=True).count(),
        'blood_stats': blood_stats, 'district_stats': district_stats,
        'dup_groups': dup_groups, 'found': found, 'q': q, 'cfg': cfg,
        'requests': DonorContactRequest.objects.select_related('receiver', 'donor_profile__user')[:15],
        'reminders': Reminder.objects.select_related('donor__user').order_by('-created_at')[:15],
        'recent_donations': DonationRecord.objects.select_related('donor__user')[:15],
    })


# ─────────────────────────── ERROR HANDLERS ───────────────────────────
def custom_404(request, exception):
    return render(request, 'errors/404.html', status=404)


def custom_500(request):
    return render(request, 'errors/500.html', status=500)
