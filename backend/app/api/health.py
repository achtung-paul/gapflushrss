# A simple health-check endpoint. Useful for:
# - confirming the backend container started correctly
# - confirming it can actually reach the database (not just that the
#   process is running)

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    # A trivial query that only succeeds if the database connection works.
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
