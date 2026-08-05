# Every SQLAlchemy model (added in later phases, e.g. User, Project,
# Analysis) will inherit from this Base class. Keeping Base in its own
# small module (instead of inside session.py) avoids import-order problems
# between Alembic, the models, and the app.

from sqlalchemy.orm import declarative_base

Base = declarative_base()
