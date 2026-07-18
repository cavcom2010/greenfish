"""Generate a VAPID keypair for Web Push notifications."""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class Command(BaseCommand):
    help = "Generate a VAPID keypair. Add the output to your .env, then restart."

    def handle(self, *args, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())

        private_value = private_key.private_numbers().private_value
        private_b64 = _b64url(private_value.to_bytes(32, "big"))

        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_b64 = _b64url(public_bytes)

        self.stdout.write("Add these to your .env file:")
        self.stdout.write("")
        self.stdout.write(f"VAPID_PUBLIC_KEY={public_b64}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private_b64}")
        self.stdout.write("VAPID_ADMIN_EMAIL=orders@yourdomain.com")
