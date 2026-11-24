"""Opportunistic scheduler: runs the same job as `manage.py run_scheduled_jobs`
at most every JOBS_MIN_INTERVAL_SECONDS per process, and never breaks a request."""
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)
_last_run = 0.0


class ScheduledJobsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _last_run
        if getattr(settings, 'RUN_JOBS_IN_REQUEST', False):
            now = time.monotonic()
            if now - _last_run > settings.JOBS_MIN_INTERVAL_SECONDS:
                _last_run = now
                try:
                    from .services import process_due_reminders, refresh_due_donors
                    refresh_due_donors()
                    process_due_reminders()
                except Exception:  # noqa: BLE001  (DB not migrated yet, etc.)
                    logger.exception('Scheduled jobs failed')
        return self.get_response(request)
