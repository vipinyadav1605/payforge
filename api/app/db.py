from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

_s = get_settings()

# Connection pooling: pool_size connections are kept open; up to max_overflow extra are
# opened under burst load and closed afterwards. pool_pre_ping drops dead connections.
engine = create_engine(
    _s.database_url,
    pool_size=_s.db_pool_size,
    max_overflow=_s.db_max_overflow,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """One session per request. Handlers/services commit explicitly; anything
    uncommitted is rolled back when the session closes."""
    with SessionLocal() as session:
        yield session
