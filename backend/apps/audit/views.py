from rest_framework.generics import ListAPIView

from apps.common.pagination import DefaultCursorPagination
from apps.common.schema import staff_schema
from apps.restaurants.models import MembershipRole
from apps.restaurants.permissions import RestaurantScopedMixin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditPagination(DefaultCursorPagination):
    ordering = ("-created_at", "-id")


@staff_schema(get="List audit entries for the restaurant (manager or owner)")
class AuditLogListView(RestaurantScopedMixin, ListAPIView):
    min_role = MembershipRole.MANAGER
    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditLogSerializer
    pagination_class = AuditPagination
