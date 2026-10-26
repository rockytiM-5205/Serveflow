from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import IdempotencyKey


class Command(BaseCommand):
    help = "Delete stored idempotency answers older than 48 hours (they hold copies of responses)."

    def handle(self, *args, **options):
        deleted, _ = IdempotencyKey.objects.filter(created_at__lt=timezone.now() - timedelta(hours=48)).delete()
        self.stdout.write(f"Deleted {deleted} expired idempotency record(s).")
