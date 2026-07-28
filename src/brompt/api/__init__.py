"""REST API for Brompt Engine — prompt generation, feedback, and reports."""

from .routes import create_app

__all__ = ["create_app"]
