from .models import AuditLog


def record(*, restaurant, actor, action, entity_type, entity_id, metadata=None):
    """Write an audit entry. Call inside the same transaction as the change it describes."""
    return AuditLog.objects.create(
        restaurant=restaurant,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata or {},
    )
