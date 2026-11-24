"""
Management command to create sample donor data for testing.
Usage: python manage.py create_sample_data
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import DonorProfile
from core.services import record_donation, recalc_donor
from datetime import date, timedelta
import random


SAMPLE_DONORS = [
    {"name": "Arun Kumar", "mobile": "9876543201", "bg": "O+", "district": "ernakulam", "locality": "Kaloor"},
    {"name": "Priya Nair", "mobile": "9876543202", "bg": "A+", "district": "thiruvananthapuram", "locality": "Pettah"},
    {"name": "Suresh Menon", "mobile": "9876543203", "bg": "B+", "district": "kozhikode", "locality": "Palayam"},
    {"name": "Anitha Thomas", "mobile": "9876543204", "bg": "AB+", "district": "thrissur", "locality": "Punkunnam"},
    {"name": "Rajesh Pillai", "mobile": "9876543205", "bg": "O-", "district": "kollam", "locality": "Chinnakada"},
    {"name": "Meera Krishnan", "mobile": "9876543206", "bg": "A-", "district": "palakkad", "locality": "Walayar"},
    {"name": "Sanjay Varma", "mobile": "9876543207", "bg": "B-", "district": "malappuram", "locality": "Manjeri"},
    {"name": "Deepa Mohan", "mobile": "9876543208", "bg": "AB-", "district": "kannur", "locality": "Thaliparamba"},
    {"name": "Anil Jose", "mobile": "9876543209", "bg": "O+", "district": "kottayam", "locality": "Changanacherry"},
    {"name": "Lakshmi Devi", "mobile": "9876543210", "bg": "A+", "district": "alappuzha", "locality": "Alappuzha Town"},
    {"name": "Vinod Rajan", "mobile": "9876543211", "bg": "B+", "district": "idukki", "locality": "Munnar"},
    {"name": "Sindhu Krishnamurthy", "mobile": "9876543212", "bg": "O+", "district": "wayanad", "locality": "Kalpetta"},
    {"name": "Manoj Babu", "mobile": "9876543213", "bg": "AB+", "district": "kasaragod", "locality": "Kasaragod Town"},
    {"name": "Rekha Suresh", "mobile": "9876543214", "bg": "A-", "district": "pathanamthitta", "locality": "Pathanamthitta Town"},
    {"name": "Ravi Shankar", "mobile": "9876543215", "bg": "O+", "district": "ernakulam", "locality": "Edapally"},
]


class Command(BaseCommand):
    help = 'Creates sample donor data for testing'

    def handle(self, *args, **options):
        created = 0
        for d in SAMPLE_DONORS:
            if User.objects.filter(username=d['mobile']).exists():
                self.stdout.write(f"  Skipping {d['name']} (already exists)")
                continue

            parts = d['name'].split(' ', 1)
            user = User.objects.create_user(
                username=d['mobile'],
                password='Sanjeevani@123',
                first_name=parts[0],
                last_name=parts[1] if len(parts) > 1 else '',
            )

            donor = DonorProfile.objects.create(
                user=user,
                mobile=d['mobile'],
                date_of_birth=date(date.today().year - random.randint(20, 50), random.randint(1, 12), random.randint(1, 28)),
                blood_group=d['bg'],
                district=d['district'],
                locality=d['locality'],
                show_in_directory=True,
                share_contact=True,
                health_declaration=True,
                show_last_donation_date=random.choice([True, False]),
            )
            # Mix of recent donors (Unavailable) and older ones (Available) - status is calculated.
            days_ago = random.choice([10, 30, 60, 120, 200, 365])
            record_donation(donor, date.today() - timedelta(days=days_ago), source='admin')
            self.stdout.write(self.style.SUCCESS(f"  Created: {d['name']} ({d['bg']}) - {d['district']}"))
            created += 1

        self.stdout.write(self.style.SUCCESS(f"\n✓ Created {created} sample donors."))
        self.stdout.write("  Login with mobile number and password: Sanjeevani@123")
