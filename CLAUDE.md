# Social App — Claude Context

## What this project is
A Facebook-style social network: posts, likes, comments, friends, personalized feed,
real-time 1:1 + group chat (WebSocket), push notifications, full-text search, async
media transcoding, and a production-shaped Kubernetes deployment.

## Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Frontend | React + Vite + Tailwind + React Query |
| Primary DB | PostgreSQL via PgBouncer |
| Document store | MongoDB (replica set rs0) — messages, read receipts |
| Cache / pub-sub | Redis Sentinel — presence, feed cache, rate limiting, idempotency |
| Message broker | Kafka (Strimzi, 3 brokers) |
| Object storage | MinIO (local) / S3 (prod) |
| Search | Meilisearch |
| Push | FCM + APNs via events-worker |
| Observability | Prometheus `/metrics`, OpenTelemetry → Jaeger |
| Infra | Kubernetes (k8s/), Docker Compose (local dev) |

## Project layout
backend/app/

api/          REST + WebSocket routers
core/         config, db clients, kafka, redis, mongo, minio, observability, resilience
middleware/   rate limiting (Redis Lua token bucket), idempotency
models/       SQLAlchemy ORM models
schemas/      Pydantic schemas
services/     feed, chat, presence, read-receipt, push, search, token
workers/      chat_consumer, events_consumer, transcode_worker
backend/alembic/  migrations
frontend/         React SPA
k8s/              Kubernetes manifests

## Key architectural rules
- **Stateless backend**: no sticky sessions. WebSocket fan-out happens via Kafka
  (`chat.messages` topic, keyed by `room_id`). Every pod runs its own consumer group
  suffix so all pods receive every message.
- **Typing indicators**: Redis pub/sub (`chat:typing:{room_id}`), NOT Kafka.
- **Presence**: Redis key `presence:user:{id}`, 60s TTL refreshed every 30s.
- **Read receipts**: MongoDB `$max` upsert — never move backwards.
- **Feed**: keyset pagination (`before_id`). Friend IDs cached in Redis (60s TTL),
  invalidated on accept/reject.
- **Idempotency**: `Idempotency-Key` header cached in Redis for 24h. Refresh tokens
  stored as SHA-256 hashes; replayed token revokes the whole session family.
- **Resilience**: rate limiter and idempotency middleware **fail open**. Kafka publish
  is in try/except after the DB write — a bus failure never blocks the primary write.
- **DLQ pattern**: `consume_with_dlq` retries 3× with jitter, then routes to
  `<topic>.dlq` and commits offset.

## Kafka topics
| Topic | Partitions | Consumer |
|---|---|---|
| `chat.messages` | 12 | Every backend pod (fan-out) |
| `social.events` | 6 | events-worker (push, search index) |
| `media.uploaded` | — | transcode-worker (ffmpeg thumbnails + 720p) |
| `*.dlq` | — | poison-pill sink |

## Environment & local dev
```bash
cp .env.example .env
docker compose up --build
# Migrations run automatically on backend start
```
Never read or edit `.env` directly. Use `.env.example` as the reference.

## Running tests
```bash
docker compose run --rm backend pytest
```
Tests live in `backend/tests/`. Use pytest fixtures, not raw DB calls.

## Coding conventions
- Async everywhere in the backend (FastAPI async routes, async SQLAlchemy, Motor for Mongo).
- Pydantic v2 schemas. Keep schemas in `schemas/`, not inline in routers.
- New background jobs go in `workers/` and get their own Kubernetes Deployment.
- Observability: add OpenTelemetry spans for any new service-layer function.
  Prometheus counters/histograms for new API paths.
- Health vs readiness: `/health` is process-only (never add dep checks here).
  `/ready` checks Redis + Mongo.

## What NOT to do
- Don't add synchronous blocking calls inside async routes.
- Don't add Kafka publish inside a DB transaction — publish after commit.
- Don't store secrets in k8s manifests; use the `Secret` objects already wired up.
- Don't change `min.insync.replicas` or `replication.factor` without a good reason.
- Don't use `readPreference=primary` for Mongo reads — use `secondaryPreferred`.

## Known gaps (don't implement without asking)
- Outbox pattern for exactly-once Kafka delivery (currently best-effort after DB write)
- WebPush for browser notifications (only FCM/APNs/web tokens today)
- ABAC / per-room permissions beyond simple membership
- Postgres HA via CloudNativePG (currently PgBouncer pool only)