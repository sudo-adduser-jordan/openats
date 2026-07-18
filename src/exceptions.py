"""Exception hierarchy for openats."""


class AtsCollectorError(Exception):
    """Base class for all openats errors."""


class ManifestError(AtsCollectorError):
    """Raised when the dataset manifest cannot be fetched or parsed."""


class StorageError(AtsCollectorError):
    """Raised when reading from or writing to remote storage fails."""


class CollectorError(AtsCollectorError):
    """Raised when an ATS collector fails to fetch or parse jobs."""


class CompanyNotFoundError(CollectorError):
    """Raised when a company is not present on the requested ATS."""
