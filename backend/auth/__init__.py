"""Sign-in and roles. Contract for every router (docs/ARCHITECTURE.md §8):

    from backend.auth import CurrentUser, OptionalUser, AdminUser            # Annotated dependencies
    from backend.auth import current_user, optional_user, require_admin      # plain dependency functions
"""
from __future__ import annotations

from backend.auth.deps import AdminUser, CurrentUser, OptionalUser, current_user, optional_user, require_admin

__all__ = ["AdminUser", "CurrentUser", "OptionalUser", "current_user", "optional_user", "require_admin"]
