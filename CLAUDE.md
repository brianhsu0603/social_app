# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is
A Facebook-style social network: posts, likes, comments, friends, personalized feed,
real-time 1:1 + group chat (WebSocket), presence, push notifications, full-text search,
async media transcoding, and a production-shaped Kubernetes deployment.

## Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async, psycopg3), Alembic |
| Frontend | React 18 + Vite + TypeScript + Tailwind + React Query + Zustand |
| Primary DB | PostgreSQL via PgBouncer |
| Document store | MongoDB (replica set `rs0`) — chat messages, read receipts |
| Cache / pub-sub | Redis Sentinel — presence, feed cache, rate limiting, idempotency, typing indicators |
| Message broker | Kafka (Strimzi, 3 brokers) |
| Object storage | MinIO (local, distributed 4-node) / S3 (prod) |
| Search | Meilisearch |
| Push | FCM + APNs via events-worker |
| Observability | Prometheus `/metrics`, OpenTelemetry → Jaeger, Sentry |
| Infra | Kubernetes (`k8s/` prod-shaped, `local_k8s/` for local cluster testing), Terraform (`terraform/`, AWS EKS/RDS/DocumentDB/MSK/ElastiCache), Docker Compose (local dev) |

## Project layout
```
backend/app/
  api/          REST + WebSocket routers (one file per resource)
  core/         config, db clients (postgres/mongo/redis/kafka/minio), security, observability, resilience
  middleware/   rate limiting (Redis Lua token bucket), idempotency
  models/       SQLAlchemy ORM models
  schemas/      Pydantic v2 schemas
  services/     feed, chat, presence, read-receipt, push, search, token, ws_manager
  workers/      chat_consumer, events_consumer, transcode_worker (started at app boot, not separate processes)
backend/alembic/   migrations
backend/tests/     pytest, in-memory SQLite + mocked Kafka (see conftest.py) — no Docker needed to run
frontend/src/      React SPA
k8s/               production-shaped manifests (namespace, datastores, app, ingress, observability, backups, NetworkPolicies)
local_k8s/         stripped-down manifests for local cluster testing (orbstack/minikube), includes mongo/redis/kafka/minio inline
terraform/         AWS infra (EKS, RDS, DocumentDB, MSK, ElastiCache, ECR, IAM, Route53, ACM)
scripts/           init-mongo-rs.sh (one-time Mongo replica-set init)
```

## Key architectural rules
- **Stateless backend**: no sticky sessions. WebSocket fan-out happens via Kafka
  (`chat.messages` topic, keyed by `room_id`). `chat_consumer` runs in-process in every
  pod with a group id suffixed by hostname (`app/workers/chat_consumer.py`), so every
  pod's consumer receives every message and pushes to whatever local sockets it owns
  (`app/services/ws_manager.py`).
- **Typing indicators**: Redis pub/sub (`chat:typing:{room_id}`), NOT Kafka.
- **Presence**: Redis key `presence:user:{id}`, 60s TTL refreshed every 30s.
- **Read receipts**: MongoDB `$max` upsert on the high-water-mark — never move backwards.
- **Feed**: keyset pagination (`before_id`). Friend IDs cached in Redis (60s TTL),
  invalidated on accept/reject.
- **Idempotency**: `Idempotency-Key` header caches 2xx responses in Redis for 24h. Refresh
  tokens are stored as SHA-256 hashes; replaying an already-rotated token revokes the
  whole session family.
- **Resilience**: rate limiter and idempotency middleware **fail open**. Kafka publish for
  posts/comments/friends/media happens in a try/except *after* the DB write commits — a bus
  failure never blocks or rolls back the primary write.
- **DLQ pattern**: `consume_with_dlq` (`app/core/kafka_client.py`) retries a handler 3× with
  exponential backoff, then routes the payload + failure metadata to `<topic>.dlq` and
  commits the offset so one poison message can't stall the consumer group.
- **Health vs readiness**: `/health` is process-only liveness (never add dependency checks
  here). `/ready` checks Redis + Mongo and gates load-balancer routing.

## Kafka topics
| Topic | Partitions | Consumer |
|---|---|---|
| `chat.messages` | 12 | Every backend pod's in-process `chat_consumer` (fan-out) |
| `social.events` | 6 | `events_consumer` worker (push notifications, search indexing) |
| `media.uploaded` | — | `transcode_worker` (ffmpeg thumbnails + 720p) |
| `*.dlq` | — | poison-pill sink, not actively consumed |

## Environment & local dev
```bash
cp .env.example .env
docker compose up --build
```
Migrations run automatically on backend start. Never read or edit `.env` directly — use
`.env.example` as the reference.

| Service | URL |
|---|---|
| App | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |
| Meilisearch | http://localhost:7700 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |
| Jaeger UI | http://localhost:16686 |

Manual migrations:
```bash
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend alembic revision --autogenerate -m "your message"
```

## Tests & linting
```bash
docker compose run --rm backend pytest              # all backend tests
docker compose run --rm backend pytest tests/test_posts.py -k some_test  # single test
docker compose run --rm backend ruff check backend/
docker compose run --rm backend ruff format --check backend/

cd frontend && npm run lint   # tsc --noEmit
cd frontend && npm run build  # tsc -b && vite build
```
Backend tests (`backend/tests/`) don't actually need Docker/real infra: `conftest.py` spins
up an in-memory SQLite engine and mocks Kafka `publish` calls, so `pytest` also runs directly
in a local venv with `backend/requirements.txt` installed. CI (`backend-ci.yml`) lints with
ruff first and only runs tests if lint passes; it runs tests through `docker compose run` to
match local dev.

## Coding conventions
- Async everywhere in the backend (FastAPI async routes, async SQLAlchemy via psycopg3,
  Motor for Mongo).
- Pydantic v2 schemas live in `schemas/`, not inline in routers.
- New background jobs go in `workers/`, started at app boot (see `main.py` lifespan) rather
  than as separate Kubernetes deployments — `transcode_worker` is the exception with its own
  Deployment/HPA since it's CPU-bound.
- Add OpenTelemetry spans for new service-layer functions and Prometheus counters/histograms
  for new API paths.

## What NOT to do
- Don't add synchronous blocking calls inside async routes.
- Don't add a Kafka publish inside a DB transaction — publish after commit, in a try/except.
- Don't store secrets in k8s manifests; use the `Secret` objects already wired up.
- Don't change `min.insync.replicas` or `replication.factor` for Kafka without a good reason.
- Don't use `readPreference=primary` for Mongo reads — use `secondaryPreferred`.

## Known gaps (don't implement without asking)
- Outbox pattern for exactly-once Kafka delivery (currently best-effort after DB write)
- WebPush for browser notifications (only FCM/APNs/web tokens today)
- ABAC / per-room permissions beyond simple membership
- Full Postgres HA via CloudNativePG, image safety/NSFW classifier, frontend offline chat cache
