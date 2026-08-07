# Base class for every project-scoped model (Commodity and everything
# under it -- see models/commodity.py and friends). These tables live on
# whichever Postgres service a Project is assigned to (core/service_db.py),
# not the app's own central database, so they need their own declarative
# base and their own Alembic migration chain (alembic_project/) --
# keeping ProjectBase separate from db/base.py's central Base is what lets
# Alembic tell the two schemas apart.

from sqlalchemy.orm import declarative_base

ProjectBase = declarative_base()
