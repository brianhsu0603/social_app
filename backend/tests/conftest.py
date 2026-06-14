import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.api.deps import get_current_user
from app.api import posts as posts_api
from app.api import comments as comments_api
from app.api import likes as likes_api
from app.api import notifications as notifications_api
from app.models import User
from app.core.security import hash_password

# Single in-memory SQLite shared across all connections in the same process
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _tables():
    """Create all tables before each test and drop them afterwards for isolation."""
    Base.metadata.create_all(_engine)
    yield
    Base.metadata.drop_all(_engine)


@pytest.fixture(autouse=True)
def _mock_kafka():
    """Prevent real Kafka publishes in every test."""
    with (
        patch("app.api.posts.publish", new_callable=AsyncMock),
        patch("app.api.comments.publish", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
def db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user_a(db):
    u = User(
        email="alice@example.com",
        username="alice",
        display_name="Alice",
        password_hash=hash_password("secret"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user_b(db):
    u = User(
        email="bob@example.com",
        username="bob",
        display_name="Bob",
        password_hash=hash_password("secret"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def make_client(db):
    """Factory that returns a TestClient authenticated as the given user."""

    def _make(user: User) -> TestClient:
        _app = FastAPI()
        _app.include_router(posts_api.router)
        _app.include_router(comments_api.router)
        _app.include_router(likes_api.router)
        _app.include_router(notifications_api.router)
        _app.dependency_overrides[get_db] = lambda: db
        _app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(_app, raise_server_exceptions=True)

    return _make


@pytest.fixture
def client(make_client, user_a):
    """Default TestClient authenticated as user_a (alice)."""
    return make_client(user_a)
