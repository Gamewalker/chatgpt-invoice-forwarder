class InvoiceAgentError(Exception):
    """Base class for user-facing agent failures."""


class ConfigurationError(InvoiceAgentError):
    """Configuration is absent or invalid."""


class ValidationError(InvoiceAgentError):
    """A downloaded invoice did not pass validation."""


class AmbiguousDownloadError(ValidationError):
    """No unique invoice download could be identified."""


class AuthenticationRequiredError(InvoiceAgentError):
    """Interactive authentication is required before continuing."""


class PermanentSendError(InvoiceAgentError):
    """Sending cannot succeed without configuration or user action."""


class TemporarySendError(InvoiceAgentError):
    """Sending may succeed during a later retry."""

