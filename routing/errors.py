"""Typed errors for the routing package."""
from __future__ import annotations


class RoutingError(Exception):
    """Base class for every error this package raises."""


class WorldError(RoutingError):
    """The task/port data on disk is missing or inconsistent."""


class ChartError(RoutingError):
    """The sea chart is missing, stale, or cannot reach a port."""


class ModelError(RoutingError):
    """A model parameter is outside its valid range."""
