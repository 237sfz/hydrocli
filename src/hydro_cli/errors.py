from __future__ import annotations


class HydroCliError(RuntimeError):
    """Base class for user-facing CLI failures."""


class HydroAuthError(HydroCliError):
    """Authentication or session failure."""


class HydroRequestError(HydroCliError):
    """HTTP request failure."""


class HydroParseError(HydroCliError):
    """Hydro page or API parsing failure."""
