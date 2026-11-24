from django.core.management.base import BaseCommand

from core.services import recalc_all


class Command(BaseCommand):
    help = 'Recalculate availability, next eligible dates and reminders for ALL donors (use after changing eligibility settings).'

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS(f'Recalculated {recalc_all()} donors'))
