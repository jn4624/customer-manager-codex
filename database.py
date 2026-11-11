"""SQLite engine, session factory, and database initialization."""

from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
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


def get_db():
    """Provide a short-lived database session for one request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create missing tables and add the nullable employee password column."""
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("employees")}
    if "password_hash" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE employees ADD COLUMN password_hash VARCHAR"))


if __name__ == "__main__":
    init_db()
    print(f"Database ready: {DATABASE_PATH}")
    print("Tables created: customers, products, employees, orders")
