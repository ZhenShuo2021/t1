class ScrapeError(Exception):
    """All scraping related errors."""


class FileProcessingError(ScrapeError):
    """File processing fail."""


class DownloadError(ScrapeError):
    """Downloading fail."""


class SecurityError(Exception):
    """Password encryption/decryption fail."""


class BotError(Exception):
    """Web bot operation error."""
