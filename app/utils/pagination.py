import math
from typing import TypeVar, List, Sequence
from sqlalchemy.orm import Query
from app.schemas.common import PaginatedResponse

T = TypeVar("T")

def paginate(query: Query, page: int = 1, size: int = 20) -> PaginatedResponse[T]:
    if page < 1:
        page = 1
    if size < 1:
        size = 20
    elif size > 100:
        size = 100

    total = query.count()
    pages = math.ceil(total / size) if total > 0 else 1
    items: Sequence[T] = query.offset((page - 1) * size).limit(size).all()

    return PaginatedResponse(
        items=list(items),
        total=total,
        page=page,
        size=size,
        pages=pages
    )
