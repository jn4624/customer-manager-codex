import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from database import get_db
from models import Base


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test_customer.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(main, "init_db", lambda: None)
    main.app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(main.app) as client:
            yield client, test_session
    finally:
        main.app.dependency_overrides.clear()
        test_engine.dispose()
