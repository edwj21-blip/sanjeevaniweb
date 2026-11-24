"""
Business logic: availability recalculation, donation recording, reminders,
notifications and Web Push delivery.
"""
import json
import logging
import urllib.parse
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import override

from . import eligibility
from .models import (
    ActivityLog, DonationRecord, DonorProfile, EligibilitySettings,
    Notification, PushSubscription, Reminder,
)
from .translations import tr_lang

logger = logging.getLogger(__name__)


# ───────────────────────── small helpers ─────────────────────────
def log_activity(user, action, description='', request=None):
    ip = None
    if request:
        fwd = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR')
    ActivityLog.objects.create(user=user, action=action, description=description, ip_address=ip)


def create_notification(user, title, message, notif_type='general', contact_request=None):
    return Notification.objects.create(
        user=user, title=title, message=message,
        notification_type=notif_type, contact_request=contact_request,
    )


def today():
    return timezone.localdate()


# ───────────────────────── availability ─────────────────────────
@transaction.atomic
def recalc_donor(donor, on=None):
    """
    Re-derive last donation date, next eligible date and availability from the
    donation history + EligibilitySettings, then re-schedule the reminder.
    Availability is NEVER set by the donor manually.
    """
    on = on or today()
    cfg = EligibilitySettings.load()

    latest = (donor.donations.filter(status='completed')
              .order_by('-donation_date', '-id').first())
    last_date = latest.donation_date if latest else None
    interval = cfg.interval_for(latest.donation_type) if latest else cfg.whole_blood_interval_days

    result = eligibility.evaluate(
        dob=donor.date_of_birth,
        last_donation_date=last_date,
        interval_days=interval,
        hold=donor.eligibility_hold,
        health_declaration=donor.health_declaration,
        no_history_policy=cfg.no_history_policy,
        today=on,
    )

    changed = []
    for field, value in (
        ('last_donation_date', last_date),
        ('next_eligible_date', result['next_eligible_date']),
        ('is_available', result['available']),
    ):
        if getattr(donor, field) != value:
            setattr(donor, field, value)
            changed.append(field)
    if changed:
        donor.save(update_fields=changed + ['updated_at'])

    if latest and latest.next_eligible_date != result['next_eligible_date']:
        DonationRecord.objects.filter(pk=latest.pk).update(next_eligible_date=result['next_eligible_date'])

    schedule_reminder(donor, on, cfg)
    return result


def refresh_due_donors(on=None):
    """
    Automatic re-activation: any unavailable donor whose next eligible date has
    arrived is re-evaluated (and becomes Available if all conditions pass).
    Cheap enough to call on page loads and from the scheduled command.
    """
    on = on or today()
    due = DonorProfile.objects.filter(
        is_available=False, eligibility_hold=False, next_eligible_date__lte=on,
    )
    count = 0
    for donor in due:
        recalc_donor(donor, on)
        count += 1
    return count


def recalc_all(on=None):
    n = 0
    for donor in DonorProfile.objects.all():
        recalc_donor(donor, on)
        n += 1
    return n


class DonationError(ValueError):
    pass


def validate_donation_date(donor, donation_date, donation_type, exclude_pk=None, on=None):
    """Raise DonationError(code) if the date is not acceptable."""
    on = on or today()
    cfg = EligibilitySettings.load()
    if donation_date > on:
        raise DonationError('future')
    if donor.date_of_birth and donation_date < eligibility.eighteenth_birthday(donor.date_of_birth):
        raise DonationError('before_18')
    others = donor.donations.filter(status='completed')
    if exclude_pk:
        others = others.exclude(pk=exclude_pk)
    if others.filter(donation_date=donation_date).exists():
        raise DonationError('duplicate')
    window = cfg.interval_for(donation_type)
    for other in others:
        if abs((other.donation_date - donation_date).days) < window:
            raise DonationError('too_close')


@transaction.atomic
def record_donation(donor, donation_date, donation_type='whole_blood', source='self', note=''):
    """Validate, save the history record, then recalc (Unavailable immediately)."""
    validate_donation_date(donor, donation_date, donation_type)
    cfg = EligibilitySettings.load()
    record = DonationRecord.objects.create(
        donor=donor, donation_date=donation_date, donation_type=donation_type,
        source=source, note=note,
        next_eligible_date=donation_date + timedelta(days=cfg.interval_for(donation_type)),
    )
    recalc_donor(donor)
    return record


# ───────────────────────── reminders ─────────────────────────
def schedule_reminder(donor, on=None, cfg=None):
    """
    Exactly one pending reminder per donor, `reminder_days_before` days before
    the next eligible date. Obsolete pending reminders are cancelled.
    """
    on = on or today()
    cfg = cfg or EligibilitySettings.load()
    pending = donor.reminders.filter(status='pending')
    target = donor.next_eligible_date

    if not target or target <= on or donor.eligibility_hold or not donor.is_verified_adult:
        pending.update(status='cancelled')
        return None

    pending.exclude(target_date=target).update(status='cancelled')
    remind_on = max(target - timedelta(days=cfg.reminder_days_before), on)
    reminder, created = Reminder.objects.get_or_create(
        donor=donor, target_date=target, defaults={'remind_on': remind_on},
    )
    if not created and reminder.status == 'cancelled':
        reminder.status = 'pending'
        reminder.remind_on = remind_on
        reminder.save(update_fields=['status', 'remind_on'])
    elif not created and reminder.status == 'pending' and reminder.remind_on != remind_on:
        reminder.remind_on = remind_on
        reminder.save(update_fields=['remind_on'])
    return reminder


def process_due_reminders(on=None):
    """Send every reminder whose date has arrived. Safe to run concurrently."""
    on = on or today()
    stats = {'sent': 0, 'skipped': 0, 'cancelled': 0}
    for reminder in Reminder.objects.filter(status='pending', remind_on__lte=on).select_related('donor__user'):
        # claim it atomically so two workers can never send it twice
        claimed = Reminder.objects.filter(pk=reminder.pk, status='pending').update(status='processing')
        if not claimed:
            continue
        donor = reminder.donor
        if (donor.next_eligible_date != reminder.target_date or not donor.is_active
                or donor.eligibility_hold or reminder.target_date <= on):
            Reminder.objects.filter(pk=reminder.pk).update(status='cancelled')
            stats['cancelled'] += 1
            continue
        if not donor.notify_reminders:
            Reminder.objects.filter(pk=reminder.pk).update(status='skipped')
            stats['skipped'] += 1
            continue

        lang = 'en'
        title = tr_lang('Donation reminder', lang)
        body = tr_lang('Your next eligible blood donation date is approaching in seven days. '
                       'Your support can help save lives.', lang)
        notif = create_notification(donor.user, title, body, 'reminder')
        push_result = send_push_to_user(donor.user, title, body, '/dashboard/donor/')
        Reminder.objects.filter(pk=reminder.pk).update(
            status='sent', sent_at=timezone.now(), notification=notif,
            push_status=push_result[:100],
        )
        stats['sent'] += 1
    return stats


# ───────────────────────── Web Push ─────────────────────────
def push_configured():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_push_to_user(user, title, body, url='/'):
    """
    Deliver a Web Push to every active subscription of the user.
    Returns a short status string. Never raises; delivery is best-effort.
    """
    subs = list(PushSubscription.objects.filter(user=user, is_active=True))
    if not subs:
        return 'no_subscription'
    if not push_configured():
        return 'vapid_not_configured'
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return 'pywebpush_not_installed'

    payload = json.dumps({'title': title, 'body': body, 'url': url})
    ok = failed = expired = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={'endpoint': sub.endpoint,
                                   'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.VAPID_CLAIM_EMAIL},
                ttl=86400,
            )
            sub.last_success_at = timezone.now()
            sub.failure_count = 0
            sub.last_error = ''
            sub.save(update_fields=['last_success_at', 'failure_count', 'last_error'])
            ok += 1
        except WebPushException as exc:
            code = getattr(getattr(exc, 'response', None), 'status_code', None)
            sub.failure_count += 1
            sub.last_error = str(exc)[:500]
            if code in (404, 410):          # subscription expired / unsubscribed
                sub.is_active = False
                expired += 1
            else:
                failed += 1
                if sub.failure_count >= 5:
                    sub.is_active = False
            sub.save(update_fields=['failure_count', 'last_error', 'is_active'])
        except Exception as exc:  # noqa: BLE001 - never break the reminder run
            logger.warning('Push failed: %s', exc)
            failed += 1
    return f'ok={ok} failed={failed} expired={expired}'


# ───────────────────────── hospital / WhatsApp ─────────────────────────
def build_navigation_url(lat, lng, place_id=''):
    """Google Maps navigation link built from the actual selected coordinates."""
    params = {'api': '1', 'query': f'{lat},{lng}'}
    if place_id:
        params['query_place_id'] = place_id
    return 'https://www.google.com/maps/search/?' + urllib.parse.urlencode(params)


def build_whatsapp_url(donor_mobile, hospital):
    """Click-to-Chat URL with the prefilled hospital-location message."""
    message = (
        "Hello, the hospital for the blood donation is:\n\n"
        f"Hospital: {hospital.hospital_name}\n\n"
        f"Address: {hospital.full_address}\n\n"
        f"Google Maps Location: {hospital.google_maps_link}\n\n"
        "Please reach the selected hospital."
    )
    return f"https://wa.me/91{donor_mobile}?text=" + urllib.parse.quote(message)
