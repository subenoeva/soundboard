"""Errors surfaced by the remote sound library.

Kept distinct from stdlib exceptions so the CLI can catch them by type and print a
clear message instead of a stack trace — never a silent no-op.
"""

from __future__ import annotations


class NotAuthenticatedError(Exception):
    """Raised when a remote operation needs a session and none is loaded."""


class PermissionDeniedError(Exception):
    """Raised when RLS reports zero affected rows on an update or delete.

    Zero affected rows means either the row does not exist or it belongs to someone
    else — RLS makes those indistinguishable by design, so the message covers both.
    """
