import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


class Command(BaseCommand):
    help = 'Generate a VAPID key pair for Web Push and print the .env lines.'

    def handle(self, *args, **opts):
        key = ec.generate_private_key(ec.SECP256R1())
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        private = key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        self.stdout.write(f'VAPID_PUBLIC_KEY={_b64(public)}')
        self.stdout.write(f'VAPID_PRIVATE_KEY={_b64(private)}')
        self.stdout.write('VAPID_CLAIM_EMAIL=mailto:you@example.com')
