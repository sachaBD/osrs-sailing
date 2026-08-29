"""Typed errors for the routing package."""
from __future__ import annotations


class RoutingError(Exception):
    """Base class for every error this package raises."""


class CatalogueError(RoutingError):
    """The task/port data on disk is missing or inconsistent."""


class SurveyError(RoutingError):
    """The survey's distances are missing, stale, or cannot reach a port."""


class ProblemError(RoutingError):
    """A cost parameter is out of range, or an action is illegal."""
