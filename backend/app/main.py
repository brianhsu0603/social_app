import asyncio
import logging
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth,
    chat,
    comments,
    devices,
    feed,
    friends,
    likes,
    media,
    posts,
    presence,
    read_receipts,
    search,
    users,
)
from app.core.config import settings
from app.core.kafka_client import close_producer, get_producer
from app.core.minio_client import ensure_bucket
from app.core.mongo import close_mongo, get_mongo_db
from app.core.observability import install_metrics, install_tracing
from app.core.redis_client import close_redis, get_redis
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.services import read_receipt_service, search_service
from app.workers import chat_consumer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("social_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup (best-effort; never crash because an external system is slow) ----
    for label, coro in (
        ("minio", asyncio.to_thread(ensure_bucket)),
        ("kafka", get_producer()),
        ("redis", get_redis().ping()),
    ):
        try:
            await asyncio.wait_for(coro, timeout=10)
        except Exception as e:
            log.warning("%s init: %s", label, e)

    try:
        await get_mongo_db()["messages"].create_index([("room_id", 1), ("_id", -1)])
        await read_receipt_service.ensure_indexes()
    except Exception as e:
        log.warning("mongo index init failed: %s", e)

    try:
        search_service.ensure_indexes()
    except Exception as e:
        log.warning("search init failed: %s", e)

    stop_event = asyncio.Event()
    consumer_task = asyncio.create_task(
        chat_consumer.run(stop_event), name="chat-consumer"
    )

    # SIGTERM from kubelet → drain instead of dropping in-flight requests.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # not supported on Windows / some sandboxes

    yield

    # ---- shutdown ----
    log.info("shutting down")
    stop_event.set()
    consumer_task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(consumer_task), timeout=10)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass
    await close_producer()
    await close_redis()
    await close_mongo()


app = FastAPI(title="Social App API", lifespan=lifespan)

install_metrics(app)
install_tracing(app)

app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware, capacity=120, refill_per_sec=2.0)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(likes.router)
app.include_router(feed.router)
app.include_router(friends.router)
app.include_router(media.router)
app.include_router(chat.router)
app.include_router(read_receipts.router)
app.include_router(presence.router)
app.include_router(devices.router)
app.include_router(search.router)


@app.get("/health")
def health() -> dict:
    """Liveness — does the process answer at all."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    """Readiness — are the dependencies actually reachable. Kubernetes uses
    this for routing decisions, so we keep the timeout short and fail fast."""
    issues = []
    try:
        await asyncio.wait_for(get_redis().ping(), timeout=1.0)
    except Exception as e:
        issues.append(f"redis: {e}")
    try:
        await asyncio.wait_for(get_mongo_db().command("ping"), timeout=1.0)
    except Exception as e:
        issues.append(f"mongo: {e}")
    if issues:
        from fastapi import HTTPException

        raise HTTPException(503, {"status": "not ready", "issues": issues})
    return {"status": "ready"}
