"""The order status machine. Every status change goes through change_status()."""
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record
from apps.common.exceptions import Conflict

from .models import ActorType, Order, OrderStatus, OrderStatusEvent

S = OrderStatus
LEGAL = {
    S.PENDING: {S.CONFIRMED, S.REJECTED, S.CANCELLED},
    S.CONFIRMED: {S.SERVING, S.CANCELLED},
    S.SERVING: {S.SERVED, S.CANCELLED},
}
REASON_REQUIRED = {S.REJECTED, S.CANCELLED}
MANAGER_ACTORS = {ActorType.MANAGER, ActorType.OWNER}


def actor_type_for(role):
    return ActorType(role)  # membership roles share names with the staff actor types


def change_status(*, order, to_status, actor_type, actor_user=None, reason="", expected_status=None, acknowledge_serving=False):
    """Move an order to `to_status`, or raise.

    Customers may only cancel a PENDING order. Staff cancel before SERVING; cancelling an order
    that is already being served needs a manager or owner who explicitly acknowledges it.
    The order row is locked, so two people acting at once cannot both succeed.
    """
    reason = (reason or "").strip()
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        current = locked.status

        if expected_status and current != expected_status:
            raise Conflict(
                "This order has changed since you opened it.", code="stale_status", details={"current_status": current}
            )
        if to_status not in LEGAL.get(current, set()):
            raise Conflict(
                f"An order that is {OrderStatus(current).label.lower()} can't become "
                f"{OrderStatus(to_status).label.lower()}.",
                code="invalid_transition",
                details={"from": current, "to": to_status},
            )
        if actor_type == ActorType.CUSTOMER and not (current == S.PENDING and to_status == S.CANCELLED):
            raise Conflict("Only a pending order can be cancelled.", code="invalid_transition", details={"from": current, "to": to_status})
        if current == S.SERVING and to_status == S.CANCELLED:
            if actor_type not in MANAGER_ACTORS:
                raise PermissionDenied(
                    "Only managers and owners can cancel an order that is already being served.", code="manager_required"
                )
            if not acknowledge_serving:
                raise ValidationError({"acknowledge_serving": ["Confirm that you want to cancel an order that is being served."]})
        if to_status in REASON_REQUIRED and actor_type != ActorType.CUSTOMER and not reason:
            raise ValidationError({"reason": ["Give a reason."]})

        locked.status = to_status
        locked.save(update_fields=["status", "updated_at"])
        OrderStatusEvent.objects.create(
            order=locked, restaurant=locked.restaurant, from_status=current, to_status=to_status,
            actor_type=actor_type, actor_user=actor_user, reason=reason,
        )
        if current == S.SERVING and to_status == S.CANCELLED:
            record(
                restaurant=locked.restaurant, actor=actor_user, action="order.cancelled_while_serving",
                entity_type="order", entity_id=locked.pk, metadata={"code": locked.code, "reason": reason},
            )
    return locked
