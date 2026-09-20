"""Domain-specific exception hierarchy.

Every failure mode the pipeline can hit maps to a distinct class so that callers
(and the CLI) can distinguish, for example, a missing API key from an upstream
schema change without parsing error strings.
"""

from __future__ import annotations

from typing import Any


class ElectionDataError(Exception):
    """Base class for all electiondata errors."""


class ConfigurationError(ElectionDataError):
    """Missing or invalid configuration (paths, environment variables)."""


class UnknownSourceError(ElectionDataError):
    """A dataset id that is not present in the source registry."""


class NetworkError(ElectionDataError):
    """Connection-level failure (DNS, timeout, TLS) after retries were exhausted."""


class HTTPError(ElectionDataError):
    """The server answered with an unexpected HTTP status."""

    def __init__(self, message: str, status_code: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class AuthenticationError(HTTPError):
    """401/403 or an API key that is required but not configured."""


class DatasetUnavailableError(ElectionDataError):
    """The requested dataset/table/year does not exist (upstream 404 or never ingested)."""


class SchemaChangeError(ElectionDataError):
    """The upstream file no longer matches the columns the parser expects."""


class ParserError(ElectionDataError):
    """A raw artifact could not be parsed into a table."""


class NormalizationError(ElectionDataError):
    """A parsed table could not be mapped onto the canonical schema."""


class ValidationError(ElectionDataError):
    """Data-quality rules failed with severity=error."""

    def __init__(self, message: str, report: Any = None):
        super().__init__(message)
        self.report = report


class StorageError(ElectionDataError):
    """Parquet/DuckDB/manifest write or read failure."""


class PointInTimeError(ElectionDataError):
    """A point-in-time filter could not be applied safely (e.g. no publication dates)."""
