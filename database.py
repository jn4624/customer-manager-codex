"""SQLite engine, session factory, and database initialization."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from models import Base

DATABASE_PATH = Path(__file__).resolve().with_name("customer.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, echo=False)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite leaves foreign-key checks disabled unless enabled per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables declared in models.py if they do not exist."""
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print(f"Database ready: {DATABASE_PATH}")
    print("Tables created: customers, products, employees, orders")
