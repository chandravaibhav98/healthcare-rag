"""Offset pagination shared by every list endpoint."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int = 50
    offset: int = 0
    sort: str | None = None
    descending: bool = True


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: Sequence[T]
    total: int
    limit: int
    offset: int


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    page: PageRequest,
    sortable: dict[str, InstrumentedAttribute[Any]],
    default_sort: str,
    tiebreak: InstrumentedAttribute[Any],
) -> PageResult[Any]:
    """Count, sort (whitelisted columns only) and slice `stmt`. A unique tie-breaker
    keeps pages stable when many rows share the sort value."""
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    column = sortable[page.sort or default_sort]
    order = (column.desc(), tiebreak.desc()) if page.descending else (column.asc(), tiebreak.asc())
    rows = (
        (await session.execute(stmt.order_by(*order).limit(page.limit).offset(page.offset)))
        .scalars()
        .all()
    )
    return PageResult(items=rows, total=int(total), limit=page.limit, offset=page.offset)
