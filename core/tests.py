"""
Automated tests for SANJEEVANI.   Run:  python manage.py test core -v 2
"""
import json
import sys
import types
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from . import eligibility
from .models import (
    DonationRecord, DonorContactRequest, DonorProfile, EligibilitySettings,
    HospitalLocationDetails, Notification, PushSubscription, Reminder,
)
from .services import (
    DonationError, process_due_reminders, recalc_donor, record_donation,
    refresh_due_donors, send_push_to_user, today,
)

PLAIN_STATIC = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
PW = 'pw12345!'


def years_ago(years, extra_days=0):
    t = today()
    try:
        d = t.replace(year=t.year - years)
    except ValueError:
        d = t.replace(year=t.year - years, day=28)
    return d - timedelta(days=extra_days)


def make_donor(mobile='9876500001', dob=None, last=None, bg='O+', district='alappuzha',
               declaration=True, share=True, first='Test'):
    user = User.objects.create_user(username=mobile, password=PW, first_name=first, last_name=mobile[-3:])
    donor = DonorProfile.objects.create(
        user=user, mobile=mobile, date_of_birth=dob or date(1990, 1, 1), blood_group=bg,
        district=district, locality='Town', share_contact=share, health_declaration=declaration)
    if last:
        record_donation(donor, last)
    else:
        recalc_donor(donor)
    donor.refresh_from_db()
    return donor


@override_settings(STORAGES=PLAIN_STATIC, RUN_JOBS_IN_REQUEST=False)
class Base(TestCase):
    pass


# ───────────────────────── pure rules ─────────────────────────
class EligibilityRuleTests(TestCase):
    def test_age_boundaries(self):
        self.assertEqual(eligibility.calculate_age(date(2008, 6, 15), date(2026, 6, 14)), 17)
        self.assertEqual(eligibility.calculate_age(date(2008, 6, 15), date(2026, 6, 15)), 18)
        self.assertEqual(eligibility.calculate_age(date(2008, 2, 29), date(2026, 2, 28)), 17)
        self.assertEqual(eligibility.calculate_age(date(2008, 2, 29), date(2026, 3, 1)), 18)

    def test_interval_boundary(self):
        kw = dict(dob=date(1990, 1, 1), interval_days=90, today=date(2026, 11, 23))
        self.assertTrue(eligibility.evaluate(last_donation_date=date(2026, 8, 25), **kw)['available'])
        self.assertFalse(eligibility.evaluate(last_donation_date=date(2026, 8, 26), **kw)['available'])

    def test_blank_history_is_not_assumed_eligible(self):
        kw = dict(dob=date(1990, 1, 1), interval_days=90, today=date(2026, 11, 23), last_donation_date=None)
        self.assertFalse(eligibility.evaluate(**kw)['available'])
        self.assertTrue(eligibility.evaluate(health_declaration=True, **kw)['available'])


# ───────────────────────── registration ─────────────────────────
class RegistrationTests(Base):
    def payload(self, **over):
        data = {
            'full_name': 'Anu Joseph', 'mobile': '9876543210', 'email': '', 'password': PW,
            'confirm_password': PW, 'date_of_birth': years_ago(25).isoformat(), 'blood_group': 'O+',
            'district': 'alappuzha', 'locality': 'Cherthala', 'last_donation_type': 'whole_blood',
            'share_contact': 'on', 'health_declaration': 'on', 'show_in_directory': 'on',
        }
        data.update(over)
        return data

    def test_adult_can_register(self):
        r = self.client.post('/register/', self.payload())
        self.assertRedirects(r, '/dashboard/donor/')
        d = DonorProfile.objects.get(mobile='9876543210')
        self.assertEqual(d.age, 25)
        self.assertTrue(d.is_available)            # declaration + no history + default policy

    def test_exactly_18_today_ok_and_day_before_rejected(self):
        ok = self.client.post('/register/', self.payload(mobile='9876543211', date_of_birth=years_ago(18).isoformat()))
        self.assertEqual(ok.status_code, 302)
        self.client.logout()
        bad = self.client.post('/register/', self.payload(mobile='9876543212',
                                                           date_of_birth=years_ago(18, -1).isoformat()))
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, 'You must be at least 18 years old to register as a blood donor.')
        self.assertFalse(DonorProfile.objects.filter(mobile='9876543212').exists())

    def test_under_18_message_in_malayalam(self):
        self.client.cookies['django_language'] = 'ml'
        r = self.client.post('/register/', self.payload(date_of_birth=years_ago(15).isoformat()))
        self.assertContains(r, 'കുറഞ്ഞത് 18 വയസ്സ്')
        self.assertFalse(DonorProfile.objects.exists())

    def test_duplicate_mobile_rejected(self):
        make_donor('9876543210')
        r = self.client.post('/register/', self.payload())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(DonorProfile.objects.count(), 1)

    def test_consent_required(self):
        data = self.payload(); data.pop('share_contact')
        r = self.client.post('/register/', data)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(DonorProfile.objects.exists())

    def test_registration_with_recent_donation_is_unavailable(self):
        last = today() - timedelta(days=10)
        r = self.client.post('/register/', self.payload(last_donation_date=last.isoformat()))
        self.assertEqual(r.status_code, 302)
        d = DonorProfile.objects.get()
        self.assertFalse(d.is_available)
        self.assertEqual(d.next_eligible_date, last + timedelta(days=90))
        self.assertEqual(d.donations.count(), 1)

    def test_future_last_donation_rejected(self):
        r = self.client.post('/register/', self.payload(last_donation_date=(today() + timedelta(days=2)).isoformat()))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(DonorProfile.objects.exists())


# ───────────────────────── availability engine ─────────────────────────
class AvailabilityTests(Base):
    def test_donation_makes_unavailable_immediately_and_sets_next_date(self):
        d = make_donor()
        self.assertTrue(d.is_available)
        record_donation(d, today())
        d.refresh_from_db()
        self.assertFalse(d.is_available)
        self.assertEqual(d.next_eligible_date, today() + timedelta(days=90))
        self.assertEqual(d.last_donation_date, today())

    def test_future_and_duplicate_and_too_close_rejected(self):
        d = make_donor(last=today() - timedelta(days=200))
        with self.assertRaises(DonationError):
            record_donation(d, today() + timedelta(days=1))
        with self.assertRaises(DonationError):
            record_donation(d, today() - timedelta(days=200))
        with self.assertRaises(DonationError):
            record_donation(d, today() - timedelta(days=150))

    def test_donation_before_18th_birthday_rejected(self):
        d = make_donor(dob=years_ago(20))
        with self.assertRaises(DonationError):
            record_donation(d, years_ago(19))

    def test_automatic_reactivation_without_confirmation(self):
        d = make_donor(last=today() - timedelta(days=10))
        self.assertFalse(d.is_available)
        refresh_due_donors(today() + timedelta(days=79))      # one day early
        d.refresh_from_db(); self.assertFalse(d.is_available)
        refresh_due_donors(today() + timedelta(days=80))      # day 90
        d.refresh_from_db(); self.assertTrue(d.is_available)

    def test_medical_hold_blocks_reactivation(self):
        d = make_donor(last=today() - timedelta(days=10))
        d.eligibility_hold = True; d.save()
        refresh_due_donors(today() + timedelta(days=400))
        recalc_donor(d, today() + timedelta(days=400))
        d.refresh_from_db(); self.assertFalse(d.is_available)

    def test_interval_is_configurable(self):
        cfg = EligibilitySettings.load(); cfg.whole_blood_interval_days = 120; cfg.save()
        d = make_donor(last=today())
        self.assertEqual(d.next_eligible_date, today() + timedelta(days=120))

    def test_no_history_policy_unavailable(self):
        cfg = EligibilitySettings.load(); cfg.no_history_policy = 'unavailable'; cfg.save()
        self.assertFalse(make_donor().is_available)

    def test_no_declaration_no_history_is_unavailable(self):
        self.assertFalse(make_donor(declaration=False).is_available)

    def test_profile_form_cannot_set_availability(self):
        d = make_donor(last=today())
        self.client.login(username=d.mobile, password=PW)
        self.client.post('/profile/edit/', {
            'full_name': 'Test X', 'date_of_birth': '1990-01-01', 'blood_group': 'O+', 'district': 'alappuzha',
            'locality': 'Town', 'is_available': 'on', 'share_contact': 'on', 'show_in_directory': 'on'})
        d.refresh_from_db(); self.assertFalse(d.is_available)


# ───────────────────────── reminders ─────────────────────────
class ReminderTests(Base):
    def test_one_reminder_seven_days_before(self):
        d = make_donor(last=today())
        r = Reminder.objects.get(donor=d, status='pending')
        self.assertEqual(r.target_date, today() + timedelta(days=90))
        self.assertEqual(r.remind_on, today() + timedelta(days=83))

    def test_new_donation_replaces_obsolete_reminder(self):
        d = make_donor(last=today() - timedelta(days=100))
        self.assertEqual(Reminder.objects.filter(donor=d, status='pending').count(), 0)
        record_donation(d, today())
        record_donation_extra = Reminder.objects.filter(donor=d, status='pending')
        self.assertEqual(record_donation_extra.count(), 1)

    def test_recalc_twice_does_not_duplicate(self):
        d = make_donor(last=today())
        recalc_donor(d); recalc_donor(d)
        self.assertEqual(Reminder.objects.filter(donor=d).count(), 1)

    def test_due_reminder_sent_once_with_notification(self):
        d = make_donor(last=today() - timedelta(days=10))      # next eligible in 80 days
        later = today() + timedelta(days=73)
        stats = process_due_reminders(later)
        self.assertEqual(stats['sent'], 1)
        self.assertEqual(Notification.objects.filter(user=d.user, notification_type='reminder').count(), 1)
        self.assertEqual(process_due_reminders(later)['sent'], 0)             # no duplicates
        self.assertEqual(Notification.objects.filter(user=d.user, notification_type='reminder').count(), 1)

    def test_not_sent_before_due_date(self):
        make_donor(last=today())
        self.assertEqual(process_due_reminders(today() + timedelta(days=82))['sent'], 0)

    def test_respects_notification_preference(self):
        d = make_donor(last=today() - timedelta(days=10))
        d.notify_reminders = False; d.save()
        stats = process_due_reminders(today() + timedelta(days=73))
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(Notification.objects.filter(user=d.user, notification_type='reminder').count(), 0)

    def test_scheduled_jobs_command(self):
        make_donor(last=today() - timedelta(days=10))
        call_command('run_scheduled_jobs')


# ───────────────────────── search / directory ─────────────────────────
class DirectoryTests(Base):
    def setUp(self):
        self.a = make_donor('9876500001', first='Avail1')
        self.u = make_donor('9876500002', last=today(), first='Unavail')
        self.b = make_donor('9876500003', first='Avail2')

    def test_both_available_and_unavailable_are_listed(self):
        r = self.client.get('/donors/?blood_group=O%2B&district=alappuzha')
        for name in ('Avail1', 'Unavail', 'Avail2'):
            self.assertContains(r, name)
        self.assertContains(r, 'Currently Unavailable', count=1)

    def test_call_now_only_for_available_when_logged_in(self):
        viewer = User.objects.create_user('9000000001', password=PW)
        self.client.login(username='9000000001', password=PW)
        r = self.client.get('/donors/')
        self.assertContains(r, 'js-call-btn', count=2)          # two available donors only
        self.assertNotContains(r, '9876500001')                  # donor numbers are not in the HTML
        self.assertNotContains(r, 'tel:+919876500')

    def test_anonymous_sees_login_to_call_not_numbers(self):
        r = self.client.get('/donors/')
        self.assertContains(r, 'Login to Call', count=2)
        self.assertNotContains(r, '9876500001')

    def test_unavailable_shows_next_eligible_date(self):
        r = self.client.get('/donors/?availability=unavailable')
        self.assertContains(r, 'Next Eligible Date')
        self.assertNotContains(r, 'Avail1')

    def test_filters(self):
        make_donor('9876500004', bg='AB-', district='kannur', first='Kan')
        self.assertContains(self.client.get('/donors/?blood_group=AB-'), 'Kan')
        self.assertNotContains(self.client.get('/donors/?district=alappuzha'), 'Kan')
        self.assertContains(self.client.get('/donors/?name=kan'), 'Kan')
        self.assertContains(self.client.get('/donors/?locality=tow'), 'Avail1')

    def test_donors_without_verified_age_are_not_listed(self):
        legacy = make_donor('9876500005', first='Legacy')
        DonorProfile.objects.filter(pk=legacy.pk).update(date_of_birth=None)
        self.assertNotContains(self.client.get('/donors/'), 'Legacy')

    def test_all_eight_groups_and_fourteen_districts_filter(self):
        for bg in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
            self.assertEqual(self.client.get('/donors/', {'blood_group': bg}).status_code, 200)
        from .models import KERALA_DISTRICTS
        self.assertEqual(len(KERALA_DISTRICTS), 14)
        for code, _ in KERALA_DISTRICTS:
            self.assertEqual(self.client.get('/donors/', {'district': code}).status_code, 200)

    def test_home_stats_come_from_database(self):
        r = self.client.get('/')
        c = r.context
        self.assertEqual((c['stat_total'], c['stat_available'], c['stat_unavailable']), (3, 2, 1))
        self.assertEqual(c['stat_districts'], 1)


# ───────────────────────── confirmation workflow ─────────────────────────
class ConfirmationFlowTests(Base):
    def setUp(self):
        self.donor = make_donor('9876500001')
        self.receiver = User.objects.create_user('9000000002', password=PW, first_name='Rec')
        self.rc = self.client_class(); self.rc.login(username='9000000002', password=PW)
        self.dc = self.client_class(); self.dc.login(username='9876500001', password=PW)

    def start(self):
        return self.rc.post(f'/api/call-start/{self.donor.id}/').json()

    def test_full_accept_flow(self):
        s = self.start()
        self.assertTrue(s['ok']); self.assertEqual(s['tel'], 'tel:+919876500001')
        rid = s['request_id']
        # donor sees nothing until the receiver confirms the call
        self.assertEqual(self.dc.get('/api/poll/').json()['donor_requests'], [])
        self.assertIsNotNone(self.rc.get('/api/poll/').json()['call_pending'])
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        self.assertEqual(len(self.dc.get('/api/poll/').json()['donor_requests']), 1)
        self.assertEqual(self.dc.post(f'/api/respond/{rid}/', {'action': 'accept'}).json()['status'], 'donor_confirmed')
        upd = self.rc.get('/api/poll/').json()['receiver_updates']
        self.assertEqual(upd[0]['status'], 'donor_confirmed')
        self.assertEqual(upd[0]['mobile'], '9876500001')
        # duplicate response prevented
        self.assertEqual(self.dc.post(f'/api/respond/{rid}/', {'action': 'decline'}).status_code, 409)
        req = DonorContactRequest.objects.get(pk=rid)
        self.assertEqual(req.status, 'donor_confirmed'); self.assertIsNotNone(req.donor_response_at)
        self.assertEqual(Notification.objects.filter(user=self.receiver, notification_type='donor_confirmed').count(), 1)
        # popup is shown until acknowledged
        self.rc.post(f'/api/ack/{rid}/')
        self.assertEqual(self.rc.get('/api/poll/').json()['receiver_updates'], [])

    def test_decline_flow_blocks_hospital_selection(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        self.dc.post(f'/api/respond/{rid}/', {'action': 'decline'})
        self.assertEqual(self.rc.get('/api/poll/').json()['receiver_updates'][0]['status'], 'donor_declined')
        self.assertEqual(self.rc.get(f'/hospital/{rid}/').status_code, 302)
        r = self.rc.post(f'/hospital/{rid}/save/', json.dumps({'name': 'H', 'address': 'A', 'lat': 9.9, 'lng': 76.2}),
                         content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_not_connected_never_reaches_donor(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'no'})
        self.assertEqual(self.dc.get('/api/poll/').json()['donor_requests'], [])
        self.assertEqual(DonorContactRequest.objects.get(pk=rid).status, 'not_connected')

    def test_confirm_twice_notifies_once(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        self.assertEqual(Notification.objects.filter(user=self.donor.user, notification_type='donor_request').count(), 1)

    def test_duplicate_request_reused(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        again = self.start()
        self.assertTrue(again['duplicate'])
        self.assertEqual(DonorContactRequest.objects.count(), 1)

    def test_cannot_call_unavailable_or_self_or_anonymous(self):
        record_donation(self.donor, today())
        self.assertEqual(self.rc.post(f'/api/call-start/{self.donor.id}/').status_code, 409)
        self.assertEqual(self.dc.post(f'/api/call-start/{self.donor.id}/').status_code, 400)
        anon = self.client_class()
        self.assertEqual(anon.post(f'/api/call-start/{self.donor.id}/').status_code, 302)

    def test_only_the_right_donor_can_respond(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        other = make_donor('9876500009'); oc = self.client_class(); oc.login(username='9876500009', password=PW)
        self.assertEqual(oc.post(f'/api/respond/{rid}/', {'action': 'accept'}).status_code, 404)
        self.assertEqual(self.rc.post(f'/api/respond/{rid}/', {'action': 'accept'}).status_code, 403)

    def test_only_the_receiver_can_confirm_call(self):
        rid = self.start()['request_id']
        self.assertEqual(self.dc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'}).status_code, 404)

    def test_hospital_and_whatsapp(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        self.dc.post(f'/api/respond/{rid}/', {'action': 'accept'})
        self.assertEqual(self.rc.get(f'/hospital/{rid}/').status_code, 200)
        body = {'name': 'General Hospital', 'address': 'Hospital Rd, Alappuzha', 'lat': 9.4981, 'lng': 76.3388,
                'place_id': 'ChIJabc'}
        r = self.rc.post(f'/hospital/{rid}/save/', json.dumps(body), content_type='application/json')
        self.assertTrue(r.json()['ok'])
        h = HospitalLocationDetails.objects.get(contact_request_id=rid)
        self.assertEqual((str(h.latitude), str(h.longitude)), ('9.498100', '76.338800'))
        self.assertIn('query=9.498100%2C76.338800', h.google_maps_link)
        self.assertIn('query_place_id=ChIJabc', h.google_maps_link)
        share = self.rc.get(f'/hospital/{rid}/share/')
        self.assertContains(share, 'https://wa.me/919876500001?text=')
        self.assertContains(share, 'General%20Hospital')
        self.assertContains(share, 'Please%20reach%20the%20selected%20hospital.')
        # opening WhatsApp is recorded; the donor is told in-app
        self.rc.post(f'/hospital/{rid}/location-sent/')
        self.assertEqual(DonorContactRequest.objects.get(pk=rid).status, 'location_sent')
        # other users cannot see the hospital page
        self.assertEqual(self.dc.get(f'/hospital/{rid}/share/').status_code, 404)

    def test_hospital_validation(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        self.dc.post(f'/api/respond/{rid}/', {'action': 'accept'})
        for bad in ({'name': '', 'address': 'A', 'lat': 9, 'lng': 76},
                    {'name': 'H', 'address': 'A', 'lat': 123, 'lng': 76},
                    {'name': 'H', 'address': 'A', 'lat': 'x', 'lng': 76}):
            r = self.rc.post(f'/hospital/{rid}/save/', json.dumps(bad), content_type='application/json')
            self.assertEqual(r.status_code, 400)
        self.assertFalse(HospitalLocationDetails.objects.exists())

    def test_hospital_page_without_api_key_still_loads(self):
        rid = self.start()['request_id']
        self.rc.post(f'/api/call-confirm/{rid}/', {'connected': 'yes'})
        self.dc.post(f'/api/respond/{rid}/', {'action': 'accept'})
        with override_settings(GOOGLE_MAPS_API_KEY=''):
            r = self.rc.get(f'/hospital/{rid}/')
        self.assertNotContains(r, 'maps.googleapis.com')
        with override_settings(GOOGLE_MAPS_API_KEY='TESTKEY'):
            r = self.rc.get(f'/hospital/{rid}/')
        self.assertContains(r, 'maps.googleapis.com/maps/api/js?key=TESTKEY')

    def test_csrf_is_enforced(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True); strict.login(username='9000000002', password=PW)
        self.assertEqual(strict.post(f'/api/call-start/{self.donor.id}/').status_code, 403)


# ───────────────────────── profile pages ─────────────────────────
class ProfileTests(Base):
    def test_profile_pages_render_and_update_flow(self):
        d = make_donor()
        self.client.login(username=d.mobile, password=PW)
        for url in ('/dashboard/donor/', '/profile/edit/', '/profile/donation/', '/profile/history/',
                    '/profile/notification-settings/', '/notifications/', '/dashboard/receiver/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.post('/profile/donation/', {'donation_date': today().isoformat(), 'donation_type': 'whole_blood'})
        self.assertRedirects(r, '/dashboard/donor/')
        d.refresh_from_db(); self.assertFalse(d.is_available)
        self.assertContains(self.client.get('/dashboard/donor/'), 'Unavailable')
        self.assertContains(self.client.get('/profile/history/'), today().strftime('%d %b %Y'))

    def test_future_donation_rejected_by_view(self):
        d = make_donor(); self.client.login(username=d.mobile, password=PW)
        r = self.client.post('/profile/donation/', {'donation_date': (today() + timedelta(days=1)).isoformat(),
                                                     'donation_type': 'whole_blood'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(DonationRecord.objects.count(), 0)

    def test_profile_requires_login(self):
        self.assertEqual(self.client.get('/dashboard/donor/').status_code, 302)
        self.assertEqual(self.client.get('/profile/donation/').status_code, 302)

    def test_existing_donor_without_dob_must_add_it(self):
        d = make_donor(); DonorProfile.objects.filter(pk=d.pk).update(date_of_birth=None)
        self.client.login(username=d.mobile, password=PW)
        self.assertContains(self.client.get('/dashboard/donor/'), 'Add date of birth')
        self.assertRedirects(self.client.get('/profile/donation/'), '/profile/edit/')

    def test_notification_settings_toggle(self):
        d = make_donor(); self.client.login(username=d.mobile, password=PW)
        self.client.post('/profile/notification-settings/', {})
        d.refresh_from_db(); self.assertFalse(d.notify_reminders)

    def test_receiver_signup_and_login(self):
        r = self.client.post('/signup/', {'full_name': 'Rec One', 'mobile': '9111111111', 'password': PW,
                                          'confirm_password': PW})
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.post('/login/', {'mobile': '9111111111', 'password': PW}).status_code, 302)


# ───────────────────────── push ─────────────────────────
class PushTests(Base):
    def sub(self, user, endpoint='https://push.example/abc'):
        return PushSubscription.objects.create(user=user, endpoint=endpoint, p256dh='k', auth='a')

    def test_subscribe_and_unsubscribe_endpoints(self):
        d = make_donor(); self.client.login(username=d.mobile, password=PW)
        payload = {'endpoint': 'https://push.example/xyz', 'keys': {'p256dh': 'k', 'auth': 'a'}}
        self.assertTrue(self.client.post('/push/subscribe/', json.dumps(payload), content_type='application/json').json()['ok'])
        self.assertEqual(PushSubscription.objects.filter(user=d.user, is_active=True).count(), 1)
        self.client.post('/push/subscribe/', json.dumps(payload), content_type='application/json')
        self.assertEqual(PushSubscription.objects.count(), 1)                     # no duplicates
        self.client.post('/push/unsubscribe/', json.dumps({'endpoint': payload['endpoint']}), content_type='application/json')
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_rejects_non_https_endpoint(self):
        d = make_donor(); self.client.login(username=d.mobile, password=PW)
        r = self.client.post('/push/subscribe/', json.dumps({'endpoint': 'http://x', 'keys': {'p256dh': 'k', 'auth': 'a'}}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_status_strings_without_config(self):
        d = make_donor()
        self.assertEqual(send_push_to_user(d.user, 't', 'b'), 'no_subscription')
        self.sub(d.user)
        with override_settings(VAPID_PUBLIC_KEY='', VAPID_PRIVATE_KEY=''):
            self.assertEqual(send_push_to_user(d.user, 't', 'b'), 'vapid_not_configured')

    def _fake_webpush(self, behaviour):
        mod = types.ModuleType('pywebpush')
        class WebPushException(Exception):
            def __init__(self, msg, response=None):
                super().__init__(msg); self.response = response
        mod.WebPushException = WebPushException
        mod.webpush = behaviour(WebPushException)
        return mod

    @override_settings(VAPID_PUBLIC_KEY='pub', VAPID_PRIVATE_KEY='priv')
    def test_successful_delivery_and_expired_subscription(self):
        d = make_donor()
        good, dead = self.sub(d.user, 'https://push.example/good'), self.sub(d.user, 'https://push.example/dead')

        def behaviour(Exc):
            def fake(subscription_info, **kw):
                if subscription_info['endpoint'].endswith('dead'):
                    raise Exc('gone', response=types.SimpleNamespace(status_code=410))
            return fake
        with mock.patch.dict(sys.modules, {'pywebpush': self._fake_webpush(behaviour)}):
            result = send_push_to_user(d.user, 'T', 'B', '/x')
        self.assertIn('ok=1', result); self.assertIn('expired=1', result)
        good.refresh_from_db(); dead.refresh_from_db()
        self.assertTrue(good.is_active); self.assertIsNotNone(good.last_success_at)
        self.assertFalse(dead.is_active)

    @override_settings(VAPID_PUBLIC_KEY='pub', VAPID_PRIVATE_KEY='priv')
    def test_reminder_records_push_status(self):
        d = make_donor(last=today() - timedelta(days=10)); self.sub(d.user)
        with mock.patch.dict(sys.modules, {'pywebpush': self._fake_webpush(lambda Exc: (lambda **kw: None))}):
            process_due_reminders(today() + timedelta(days=73))
        r = Reminder.objects.get(donor=d)
        self.assertEqual(r.status, 'sent'); self.assertIn('ok=1', r.push_status)

    def test_service_worker_served_at_root(self):
        r = self.client.get('/sw.js')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Service-Worker-Allowed'], '/')
        self.assertIn('javascript', r['Content-Type'])


# ───────────────────────── admin / misc ─────────────────────────
class AdminAndMiscTests(Base):
    def test_staff_dashboard_is_protected(self):
        self.assertEqual(self.client.get('/staff/dashboard/').status_code, 302)
        u = User.objects.create_user('9222222222', password=PW)
        self.client.login(username='9222222222', password=PW)
        self.assertEqual(self.client.get('/staff/dashboard/').status_code, 302)
        User.objects.create_superuser('boss', 'b@x.com', PW)
        self.client.login(username='boss', password=PW)
        make_donor()
        r = self.client.get('/staff/dashboard/?q=Test')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Total Registered Donors')

    def test_admin_donation_edit_recalculates(self):
        from django.urls import reverse
        d = make_donor(last=today())
        User.objects.create_superuser('boss', 'b@x.com', PW); self.client.login(username='boss', password=PW)
        rec = d.donations.get()
        rec.status = 'cancelled'; rec.save()
        recalc_donor(d); d.refresh_from_db()
        self.assertTrue(d.is_available); self.assertIsNone(d.last_donation_date)
        self.assertEqual(self.client.get(reverse('admin:core_donationrecord_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:core_donorprofile_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:core_eligibilitysettings_changelist')).status_code, 200)

    def test_public_pages_in_both_languages(self):
        for lang in ('en', 'ml'):
            self.client.cookies['django_language'] = lang
            for url in ('/', '/donors/', '/register/', '/login/', '/signup/', '/about/', '/contact/', '/privacy/', '/terms/'):
                self.assertEqual(self.client.get(url).status_code, 200, (lang, url))
        self.assertContains(self.client.get('/'), 'ഒരു തുള്ളി രക്തം, ഒരു പുതുജീവൻ')

    def test_language_switch(self):
        r = self.client.post('/set-language/', {'language': 'ml', 'next': '/about/'})
        self.assertEqual(r.status_code, 302)
        self.assertContains(self.client.get('/about/'), 'സഞ്ജീവനിയെക്കുറിച്ച്')

    def test_sample_data_command(self):
        call_command('create_sample_data')
        self.assertGreater(DonorProfile.objects.count(), 5)

    def test_no_whatsapp_confirmation_routes_remain(self):
        for url in ('/whatsapp-confirmation/1/', '/mark-whatsapp-sent/1/', '/hospital-location/1/'):
            self.assertEqual(self.client.get(url).status_code, 404, url)


class MigrationConsistencyTests(TestCase):
    def test_models_match_migrations(self):
        """Fails if the hand-written migration 0002 differs from the models."""
        call_command('makemigrations', '--check', '--dry-run', verbosity=0)
