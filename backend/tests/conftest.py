import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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
_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = async_sessionmaker(
    bind=_engine, autoflush=False, expire_on_commit=False
)


@pytest.fixture(autouse=True)
async def _tables():
    """Create all tables before each test and drop them afterwards for isolation."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _mock_kafka():
    """Prevent real Kafka publishes in every test."""
    with (
        patch("app.api.posts.publish", new_callable=AsyncMock),
        patch("app.api.comments.publish", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
async def db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
async def user_a(db: AsyncSession):
    u = User(
        email="alice@example.com",
        username="alice",
        display_name="Alice",
        password_hash=hash_password("secret"),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
async def user_b(db: AsyncSession):
    u = User(
        email="bob@example.com",
        username="bob",
        display_name="Bob",
        password_hash=hash_password("secret"),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
def make_client(db: AsyncSession):
    """Factory that returns an AsyncClient authenticated as the given user."""

    def _make(user: User) -> AsyncClient:
        _app = FastAPI()
        _app.include_router(posts_api.router)
        _app.include_router(comments_api.router)
        _app.include_router(likes_api.router)
        _app.include_router(notifications_api.router)

        async def _override_get_db():
            yield db

        _app.dependency_overrides[get_db] = _override_get_db
        _app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=_app), base_url="http://test")

    return _make


@pytest.fixture
def client(make_client, user_a):
    """Default AsyncClient authenticated as user_a (alice)."""
    return make_client(user_a)
