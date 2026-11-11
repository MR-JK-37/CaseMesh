from enum import Enum


class AdapterStatus(str, Enum):
    """Section 3's allowed statuses. No adapter method is ever allowed to
    return a fabricated success when status isn't LIVE — see
    NotConfiguredError below."""

    LIVE = "LIVE"
    SANDBOX = "SANDBOX"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"


def is_adapter_operational(status: AdapterStatus) -> bool:
    """Return True if adapter is in an active working state (LIVE or SANDBOX)."""
    return status in (AdapterStatus.LIVE, AdapterStatus.SANDBOX)


def is_adapter_live(status: AdapterStatus) -> bool:
    """Return True if adapter is strictly in LIVE production mode."""
    return status == AdapterStatus.LIVE


def get_adapter_status_values() -> list[str]:
    """Return all valid AdapterStatus string values."""
    return [s.value for s in AdapterStatus]


def is_adapter_configured(status: AdapterStatus) -> bool:
    """Return True if adapter is configured (LIVE, SANDBOX, or UNAVAILABLE)."""
    return status != AdapterStatus.NOT_CONFIGURED




class NotConfiguredError(RuntimeError):
    """Raised by every adapter method when the adapter isn't configured,
    instead of returning invented data. Section 0 rule 2: 'An integration
    that is not configured returns NOT_CONFIGURED; it never returns a
    fabricated or simulated success.'"""


class AdapterUnavailableError(RuntimeError):
    """Raised when an external service is configured but currently unreachable."""


class AdapterTimeoutError(AdapterUnavailableError):
    """Raised when an external service request exceeds its allotted deadline."""


class AdapterAuthError(RuntimeError):
    """Raised when external adapter credentials fail authentication."""


class AdapterPayloadError(RuntimeError):
    """Raised when external adapter response cannot be parsed or is malformed."""
