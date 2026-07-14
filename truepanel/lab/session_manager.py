"""
Project Stargate Laboratory Session Manager.

Provides the shared laboratory SessionService instance used by the CLI.
"""

from __future__ import annotations

from truepanel.lab.session_service import SessionService

#
# One laboratory.
# One active session.
#
_session_service = SessionService()


def session_service() -> SessionService:
    """Return the shared laboratory session service."""
    return _session_service
