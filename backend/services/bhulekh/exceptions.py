"""Errors raised by the UP Bhulekh Selenium integration."""


class BhulekhError(Exception):
    """Base class for Bhulekh scraper failures."""


class BhulekhTimeoutError(BhulekhError):
    """Page or element did not become ready within the configured timeout."""


class BhulekhNotFoundError(BhulekhError):
    """No khasra / record row was returned for the given inputs."""


class BhulekhCaptchaError(BhulekhError):
    """Captcha is required and could not be satisfied automatically."""


class BhulekhNavigationError(BhulekhError):
    """Could not reach the khasra search form (portal layout changed or blocked)."""
