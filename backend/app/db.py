from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Route handlers commit explicitly; if one raises before doing so
        # (or a route re-raises after a caught exception), don't leave a
        # dangling transaction for close() to paper over implicitly.
        db.rollback()
        raise
    finally:
        db.close()
