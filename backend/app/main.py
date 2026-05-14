import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, comments, feed, friends, likes, media, posts, users
from app.core.config import settings
from app.core.kafka_client import close_producer, get_producer
from app.core.minio_client import ensure_bucket
from app.core.mongo import close_mongo, get_mongo_db
from app.core.redis_client import close_redis
from app.workers import chat_consumer


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("social_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup ----
    try:
        ensure_bucket()
    except Exception as e:
        log.warning("minio not ready: %s", e)

    try:
        await get_producer()
    except Exception as e:
        log.warning("kafka producer not ready: %s", e)

    try:
        await get_mongo_db()["messages"].create_index([("room_id", 1), ("_id", -1)])
    except Exception as e:
        log.warning("mongo index creation failed: %s", e)

    stop_event = asyncio.Event()
    consumer_task = asyncio.create_task(chat_consumer.run(stop_event))

    yield

    # ---- shutdown ----
    stop_event.set()
    consumer_task.cancel()
    try:
        await consumer_task
    except (asyncio.CancelledError, Exception):
        pass
    await close_producer()
    await close_redis()
    await close_mongo()


app = FastAPI(title="Social App API", lifespan=lifespan)

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
