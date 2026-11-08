from enum import Enum


class AdapterStatus(str, Enum):
    """Section 3's allowed statuses. No adapter method is ever allowed to
    return a fabricated success when status isn't LIVE — see
    NotConfiguredError below."""

    LIVE = "LIVE"
    SANDBOX = "SANDBOX"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"


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
