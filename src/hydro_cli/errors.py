from __future__ import annotations


class HydroCliError(RuntimeError):
    """Base class for user-facing CLI failures."""


class HydroAuthError(HydroCliError):
    """Authentication or session failure."""


class HydroRequestError(HydroCliError):
    """HTTP request failure."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_text: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class HydroParseError(HydroCliError):
    """Hydro page or API parsing failure."""
