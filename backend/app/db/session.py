# Database engine and session setup.
#
# `engine` is the thing that actually talks to Postgres.
# `SessionLocal` creates a new database session (a "conversation" with the
# database) each time it's called.
# `get_db` is a FastAPI dependency: routes that need database access will
# take a `db: Session = Depends(get_db)` argument, and FastAPI will call
# this function to hand them a session, then close it afterwards.

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
