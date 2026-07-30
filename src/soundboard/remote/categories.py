"""CRUD for the shared category taxonomy."""

from __future__ import annotations

from typing import Any

from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.models import Category, RemoteClient, Session


def _row_to_category(row: dict[str, Any]) -> Category:
    return Category(
        id=row["id"],
        name=row["name"],
        color=row.get("color"),
        position=row.get("position", 0),
        created_by=row["created_by"],
    )


def add_category(
    client: RemoteClient, session: Session, name: str, color: str | None = None
) -> Category:
    existing = client.select("categories", filters={"name": name})
    if existing:
        return _row_to_category(existing[0])
    row = client.insert(
        "categories", {"name": name, "color": color, "position": 0, "created_by": session.user_id}
    )
    return _row_to_category(row)


def list_categories(client: RemoteClient) -> list[Category]:
    return [_row_to_category(row) for row in client.select("categories", filters=None)]


def remove_category(client: RemoteClient, name: str) -> None:
    rows = client.select("categories", filters={"name": name})
    if not rows:
        raise LookupError(f"no category named {name!r}")
    affected = client.delete("categories", rows[0]["id"])
    if affected == 0:
        raise PermissionDeniedError(f"cannot delete category {name!r}: not yours")
