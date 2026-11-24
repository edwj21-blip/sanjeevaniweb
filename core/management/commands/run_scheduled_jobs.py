import time

from django.core.management.base import BaseCommand

from core.services import process_due_reminders, refresh_due_donors


class Command(BaseCommand):
    help = ('Re-activate donors whose next eligible date has arrived and send due '
            'seven-day reminders. Run once (cron / Task Scheduler) or keep it running with --loop SECONDS.')

    def add_arguments(self, parser):
        parser.add_argument('--loop', type=int, default=0, metavar='SECONDS',
                            help='Keep running and repeat every SECONDS (e.g. 600).')

    def run_once(self):
        n = refresh_due_donors()
        stats = process_due_reminders()
        self.stdout.write(self.style.SUCCESS(f'Donors re-evaluated: {n}; reminders: {stats}'))

    def handle(self, *args, **opts):
        if not opts['loop']:
            return self.run_once()
        self.stdout.write(f"Scheduler running every {opts['loop']} s. Press Ctrl+C to stop.")
        while True:
            try:
                self.run_once()
            except Exception as exc:  # keep the loop alive
                self.stderr.write(f'Job failed: {exc}')
            time.sleep(opts['loop'])
