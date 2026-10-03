"""Shared FastAPI dependencies.

`get_db` yields one psycopg connection per request (commit on success, rollback
on error, handled by `backend.db.get_conn`). Tests replace it with
`app.dependency_overrides[get_db] = lambda: fake_conn`.
"""
from __future__ import annotations

import inspect
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Annotated, Any

from fastapi import Depends


def get_db() -> Iterator[Any]:
    """Yield an open DB connection for the duration of the request."""
    from backend import db  # lazy: keeps `import backend.main` free of psycopg

    with db.get_conn() as conn:
        yield conn


try:  # scope="function" (FastAPI >= 0.121) commits *before* the response is sent
    _db_dependency = Depends(get_db, scope="function")
except TypeError:  # pragma: no cover - older FastAPI
    _db_dependency = Depends(get_db)

DB = Annotated[Any, _db_dependency]


@contextmanager
def db_session(app: Any) -> Iterator[Any]:
    """Open a connection only when needed (e.g. the final /rides/stream chunk). Honours dependency_overrides."""
    made = app.dependency_overrides.get(get_db, get_db)()
    if inspect.isgenerator(made):
        with contextmanager(lambda: made)() as conn:
            yield conn
    else:
        yield made


@contextmanager
def savepoint(conn: Any) -> Iterator[None]:
    """Nested transaction (SAVEPOINT) so one failing statement doesn't abort the request's transaction."""
    tx = getattr(conn, "transaction", None)
    with tx() if callable(tx) else nullcontext():
        yield
