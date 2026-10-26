from django.conf import settings
from django.db import models

from apps.restaurants.models import Restaurant


class AuditLog(models.Model):
    """Who did what to which record. Append-only: the admin shows it read-only.

    Keep `metadata` free of passwords, tokens and personal details.
    """

    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64)
    entity_id = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["restaurant", "-created_at"], name="audit_restaurant_recent_idx")]

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id}"
