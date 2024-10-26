class ScrapeError(Exception):
    """All scraping related errors."""


class FileProcessingError(ScrapeError):
    """File processing fail."""


class DownloadError(ScrapeError):
    """Downloading fail."""
