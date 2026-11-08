import uuid


def new_id(prefix: str) -> str:
    """Public, type-prefixed id such as pay_3f9c... (like Stripe's)."""
    return f"{prefix}_{uuid.uuid4().hex[:24]}"
