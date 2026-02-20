"""Custom exceptions for the converter library."""


class ConverterError(Exception):
    """Base exception for converter errors."""

    pass


class FileNotFoundError(ConverterError):
    """Raised when input file is not found."""

    pass


class InvalidExodusFileError(ConverterError):
    """Raised when the file is not a valid Exodus II file."""

    pass


class ConversionError(ConverterError):
    """Raised when conversion fails."""

    pass


class UnsupportedFeatureError(ConverterError):
    """Raised when a requested feature is not supported."""

    pass
