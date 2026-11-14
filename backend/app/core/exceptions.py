class NotYetImplemented(NotImplementedError):
    """Raised by interfaces whose implementation is planned for a later phase.

    The API maps this to HTTP 501 so callers never receive fabricated results.
    """

