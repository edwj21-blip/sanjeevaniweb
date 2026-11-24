"""
Pure-Python age and donor-eligibility rules (no Django imports, so they are
easy to unit-test).  The interval is always passed in from EligibilitySettings
(editable in the admin) - nothing here hardcodes a medical period.
"""
from datetime import date, timedelta

MIN_DONOR_AGE = 18


def calculate_age(dob, today=None):
    """Exact age in whole years, respecting whether the birthday has passed."""
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def adult_cutoff(today=None):
    """Latest date of birth that makes someone at least 18 today."""
    today = today or date.today()
    try:
        return date(today.year - MIN_DONOR_AGE, today.month, today.day)
    except ValueError:  # 29 Feb in a non-leap target year
        return date(today.year - MIN_DONOR_AGE, 2, 28)


def is_adult(dob, today=None):
    return dob is not None and calculate_age(dob, today) >= MIN_DONOR_AGE


def eighteenth_birthday(dob):
    try:
        return date(dob.year + MIN_DONOR_AGE, dob.month, dob.day)
    except ValueError:  # born 29 Feb
        return date(dob.year + MIN_DONOR_AGE, 3, 1)


def evaluate(*, dob, last_donation_date, interval_days, hold=False,
             health_declaration=False, no_history_policy='available', today=None):
    """
    Decide availability.  Returns dict(available, next_eligible_date, reason).
    reason is one of: no_dob, underage, hold, waiting, eligible,
    no_history_ok, no_history_blocked.
    """
    today = today or date.today()
    next_date = None
    if last_donation_date:
        next_date = last_donation_date + timedelta(days=interval_days)

    if dob is None:
        return dict(available=False, next_eligible_date=next_date, reason='no_dob')
    if not is_adult(dob, today):
        return dict(available=False, next_eligible_date=next_date, reason='underage')
    if hold:
        return dict(available=False, next_eligible_date=next_date, reason='hold')

    if last_donation_date:
        if today >= next_date:
            return dict(available=True, next_eligible_date=next_date, reason='eligible')
        return dict(available=False, next_eligible_date=next_date, reason='waiting')

    # No previous donation recorded: never assume eligibility just because blank.
    if no_history_policy == 'available' and health_declaration:
        return dict(available=True, next_eligible_date=None, reason='no_history_ok')
    return dict(available=False, next_eligible_date=None, reason='no_history_blocked')
