class NotYetImplemented(NotImplementedError):
    """Raised by interfaces whose implementation is planned for a later phase.

    The API maps this to HTTP 501 so callers never receive fabricated results.
    """


class DataSufficiencyError(Exception):
    """Raised when ground truth or satellite observations are statistically insufficient.

    Specifically used to block supervised ML training or empirical threshold
    calibration when positive sample diversity or class balance is inadequate,
    preventing severe spatial overfitting.
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


