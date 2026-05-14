# Social App

A Facebook-style social network: posts (text/image/video), likes, comments, friends, a personalized feed, presence, real-time 1:1 + group chat with typing indicators and read receipts, push notifications, full-text search, async media transcoding, and a production-shaped Kubernetes deployment.

## Architecture

```
                        ┌──────────────────┐
                        │   React SPA      │   (nginx, 3+ replicas, anti-affinity)
                        └────────┬─────────┘
                                 │ HTTPS / WSS
                  ┌──────────────▼──────────────┐
                  │  Ingress (nginx-ingress)    │   TLS termination, WS upgrade
                  └────┬─────────────────┬──────┘
                       │                 │
              ┌────────▼────┐    ┌───────▼────────┐
              │   Backend   │    │  ⚙ metrics    │   Prometheus scrapes /metrics
              │  (FastAPI)  │    │  ◇ tracing    │   OTLP → Jaeger / Tempo
              │  3..20 pods │    └───────┬────────┘
              │  HPA + PDB  │            │
              └────┬───┬────┘            │
                   │   │  WS fan-out via Kafka (one consumer per pod)
                   │   └────────────────────┐
                   │                        │
   ┌───────────────┼────────────┐           │
   ▼               ▼            ▼           ▼
┌──────┐  ┌──────────────┐  ┌──────┐  ┌──────────────┐
│ Pg   │  │ Mongo replica│  │Redis │  │ Kafka        │
│ +    │  │ set (rs0)    │  │  +   │  │ (Strimzi,    │
│ Pg-  │  │ messages,    │  │Sent- │  │ 3 brokers,   │
│Boun- │  │ reads        │  │inel  │  │ replication=3│
│cer   │  └──────────────┘  └──────┘  │ min ISR=2)   │
└──────┘                              └──┬─┬─┬─┬─────┘
                                         │ │ │ │
                                         │ │ │ └─── chat.messages ──► every backend pod (WS fan-out)
                                         │ │ └───── social.events  ──► events-worker (push, search-index)
                                         │ └─────── media.uploaded ──► transcode-worker (ffmpeg)
                                         └───────── *.dlq (poison queues)

  Object storage: MinIO distributed (4 nodes, erasure-coded) — swap for S3 in prod.
  Search: Meilisearch — indexed by events-worker.
  Push: FCM + APNs from events-worker.
  Backups: daily CronJobs of Postgres + Mongo → MinIO `backups` bucket.
```

### Chat data flow (with presence + typing + receipts)

1. Client opens `WSS /chat/ws/{room_id}?token=…`.
2. Server validates membership, accepts the socket, marks the user online in Redis (`presence:user:{id}`, 60s TTL refreshed every 30s).
3. Inbound `{type: "message"}` → persisted to MongoDB → published to Kafka `chat.messages` keyed by `room_id` (per-room ordering).
4. Every backend pod runs its own consumer group with a unique suffix so each pod sees every message; each pushes to the local sockets it owns. No sticky sessions required.
5. `{type: "typing"}` is published on the Redis pub/sub channel `chat:typing:{room_id}` and bridged into every socket subscribed to that room.
6. Read receipts are upserted into Mongo's `reads` collection with `$max` so they can never go backwards. `GET /chat/rooms/{id}/unread` is a single `count_documents` past the high-water-mark.

## Features

| Area | What's there |
|---|---|
| **Auth** | Register, login, JWT access tokens, single-use rotating **refresh tokens** with replay detection, logout/revoke |
| **Posts** | Text / image / video, like, unlike, comment, delete |
| **Feed** | Self + friends timeline, friend-id cache in Redis, keyset pagination (`before_id`) |
| **Friends** | Send / accept / reject / cancel requests, auto-accept on mutual send |
| **Media** | Upload to MinIO; `media.uploaded` event triggers async transcoding → image thumbnails, 720p video + poster |
| **Chat** | 1:1 and group rooms, WebSocket realtime + REST fallback, typing indicators, presence (online/offline), unread counts, read receipts |
| **Push** | Device registration (FCM / APNs / web); events-worker dispatches notifications on `post.created`, `comment.created`, `friend.accepted` |
| **Search** | Meilisearch indexes for posts + users; one search endpoint |
| **Observability** | Prometheus `/metrics` (RED + WS/Kafka gauges), OpenTelemetry traces (FastAPI / SQLAlchemy / Redis / httpx auto-instrumented) → Jaeger |
| **Resilience** | Rate limiting (Redis Lua token bucket), idempotency keys, retries with jitter, circuit breaker primitive, DLQ for poison Kafka messages, graceful shutdown on SIGTERM, separate `/health` (liveness) and `/ready` (deps) probes |

## Project layout

```
backend/
  app/
    api/             REST + WS routers
    core/            config, db clients, security, kafka, redis, mongo, minio,
                     observability, resilience helpers
    middleware/      rate limiting, idempotency
    models/          SQLAlchemy models
    schemas/         Pydantic
    services/        feed, chat, presence, read-receipt, push, search, token
    workers/         chat_consumer, events_consumer, transcode_worker
  alembic/           migrations
  tests/             pytest
frontend/            React + Vite + Tailwind + React Query
k8s/                 namespace, config, datastores, app, workers, ingress,
                     observability (Prom/Grafana/Jaeger), backups, NetworkPolicies
.github/workflows/   backend-ci, frontend-ci, deploy
infra/               local Prometheus config
scripts/             init-mongo-rs.sh
docker-compose.yml   local dev — everything in one command
```

## How scalability / availability / reliability / fault tolerance show up

### Scalability

| Component | Mechanism |
|---|---|
| Backend (HTTP + WS) | Stateless. HPA scales 3..20 on CPU + memory. WS fan-out via Kafka so any pod can serve any room |
| Workers | Independent deployments. Events-worker scales horizontally via Kafka consumer group rebalance. Transcode-worker has its own HPA (CPU-bound) |
| Postgres connections | PgBouncer in front: 25 connections per backend × N pods → bounded to PG's `max_connections=200` |
| Kafka throughput | 12 partitions on `chat.messages`, 6 on `social.events` → at least that much parallelism per consumer group |
| Cache | Redis Sentinel, friend-id cache (60s TTL) cuts the dominant feed query |
| Search | Meilisearch handles search load instead of forcing it onto Postgres |
| Media | MinIO distributed (4 nodes); media URLs served directly to clients, not proxied through the backend |

### Availability

| Component | Mechanism |
|---|---|
| Backend / Frontend | 3 replicas, `maxUnavailable: 0`, `PodDisruptionBudget minAvailable: 2`, anti-affinity across nodes + zones |
| Postgres | PgBouncer pool (2 replicas). For prod, swap to a managed service or CloudNativePG/Zalando for streaming replicas + automatic failover |
| Mongo | 3-node replica set, anti-affinity, PDB `minAvailable: 2` (preserves quorum). Reads can hit secondaries (`readPreference=secondaryPreferred`) |
| Redis | Sentinel topology (1 primary + 2 replicas + 3 sentinels); auto-failover on primary loss |
| Kafka | 3 brokers, `replication.factor=3`, `min.insync.replicas=2` — survives one broker loss with no data loss and no write impact |
| MinIO | 4 nodes erasure-coded (2 data + 2 parity), PDB `minAvailable: 3` |
| Probes | `/health` (liveness) is process-only so a slow dependency doesn't trigger a kill loop. `/ready` checks Redis + Mongo and gates routing |
| Pod lifecycle | `terminationGracePeriodSeconds: 60` and a 10s preStop sleep so the LB drops us before we stop accepting connections |

### Reliability

| Concern | Mechanism |
|---|---|
| Lost Kafka messages | Producer is idempotent + `acks=all`. Topics replicated 3× with min ISR 2 |
| Poison-pill events | `consume_with_dlq` retries 3× with jitter, then routes to `<topic>.dlq` and commits, so one bad record doesn't stall the group |
| Duplicate writes from client retries | `Idempotency-Key` middleware caches 2xx responses in Redis for 24h |
| Replayed refresh tokens | Stored as SHA-256 hashes; presenting an already-rotated token revokes the whole session family |
| Read-receipt regression | Mongo `$max` on the high-water-mark — receipts can never move backwards |
| Friend-cache staleness | Invalidated on accept/reject; 60s TTL bounds the worst case |
| Bus failures don't break writes | Post / comment / friend / media writers publish to Kafka in a try/except — the durable write to the DB has already happened |

### Fault tolerance

| Failure | What happens |
|---|---|
| One backend pod dies | LB drops it; HPA refills; in-flight chat sockets reconnect via auto-retry from the React hook |
| One Kafka broker dies | min ISR=2 still satisfied → continued reads and writes; replication catches up the lost replica when it returns |
| Primary Redis dies | Sentinel quorum promotes a replica; rate-limit middleware fails open during the gap so the API stays available |
| Redis unreachable entirely | Rate limiter fails open; idempotency middleware passes through |
| Meilisearch down | Search endpoint returns empty; index_post/index_user log and continue |
| FCM/APNs down or unconfigured | push_service falls through to dry-run logging; the comment / post / friendship is unaffected |
| ffmpeg job fails | Retried 3× by the worker, then dead-lettered to `media.uploaded.dlq`; the original asset is untouched and the post is already viewable |
| Postgres node loss | Backend → PgBouncer fails new connections briefly; in prod a managed primary takes over within seconds |
| Mongo primary loss | Replica set elects new primary in seconds; readers using `secondaryPreferred` keep serving |
| Whole-cluster restore | Daily backups in MinIO `backups/postgres/` and `backups/mongo/`; restore script is a `pg_restore` / `mongorestore` from the latest archive |

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| App | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 (login: `minioadmin` / `minioadmin`) |
| Meilisearch | http://localhost:7700 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 (anon admin) |
| Jaeger UI | http://localhost:16686 |

Migrations run automatically on backend start. To run them manually:

```bash
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend alembic revision --autogenerate -m "your message"
```

## Run tests

```bash
docker compose run --rm backend pytest
```

## Deploy to Kubernetes

The manifests assume:
- nginx-ingress installed
- a `StorageClass` set as default
- a CNI that enforces NetworkPolicies (Calico, Cilium, …)
- the [Strimzi](https://strimzi.io) operator for Kafka

```bash
# 1. Install Strimzi (Kafka operator) once per cluster
kubectl create namespace strimzi
kubectl -n strimzi apply -f \
  'https://strimzi.io/install/latest?namespace=strimzi'

# 2. Push images (CI does this on push to main)
export REG=ghcr.io/your-org
docker build -t $REG/social-backend:latest ./backend && docker push $REG/social-backend:latest
docker build -t $REG/social-frontend:latest \
  --build-arg VITE_API_URL=https://api.example.com \
  --build-arg VITE_WS_URL=wss://api.example.com \
  ./frontend && docker push $REG/social-frontend:latest

# 3. Apply manifests in order
kubectl apply -f k8s/

# 4. One-time Mongo replica-set init
scripts/init-mongo-rs.sh

# 5. Check
kubectl -n social get pods
```

Update `MINIO_PUBLIC_ENDPOINT` in `k8s/10-config.yaml` to your public MinIO/S3 URL, and DNS for `api.example.com` + `app.example.com` to point at your ingress.

## CI/CD

- **`backend-ci.yml`** — pytest on PR, builds + pushes Docker image to GHCR on `main`.
- **`frontend-ci.yml`** — TypeScript build on PR, ships nginx-served SPA image on `main`.
- **`deploy.yml`** — triggers on successful CI, `kubectl apply -f k8s/`, rolls deployments.

Required repo secret: `KUBECONFIG` (base64-encoded kubeconfig for the target cluster).

## API surface

| Method | Path | What |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | Returns access + refresh token pair |
| POST | `/auth/refresh`, `/auth/logout` | Rotate / revoke refresh token |
| GET | `/auth/me` | Current user |
| GET / PATCH | `/users/...`, `/users/me` | Profile read / update |
| POST / GET / DELETE | `/posts`, `/posts/{id}`, `/posts/user/{id}` | Posts |
| POST / DELETE | `/posts/{id}/like` | Like / unlike |
| GET / POST / DELETE | `/posts/{id}/comments`, `/comments/{id}` | Comments |
| GET | `/feed` | Friend timeline (keyset) |
| `/friends/...` | | Friend requests, list friends |
| POST | `/media/upload` | Upload to MinIO; fires `media.uploaded` |
| `/chat/rooms`, `/chat/rooms/{id}/messages` | | Rooms + REST send |
| POST | `/chat/rooms/{id}/read` | Mark up to a message id |
| GET | `/chat/rooms/{id}/receipts`, `/chat/rooms/{id}/unread` | Receipts + unread count |
| WS | `/chat/ws/{room_id}?token=…` | Live chat + typing |
| POST / DELETE | `/devices`, `/devices/{token}` | Push token register / unregister |
| GET | `/presence?user_ids=…` | Online status batch |
| GET | `/search?q=…` | Full-text across users + posts |
| GET | `/health`, `/ready` | Liveness / readiness |
| GET | `/metrics` | Prometheus |

## Headers worth knowing

| Header | Purpose |
|---|---|
| `Authorization: Bearer <access_token>` | Standard auth |
| `Idempotency-Key: <uuid>` | Safe retries on POST/PUT/PATCH; cached 24h in Redis |
| `Retry-After` (response) | Set on 429 when rate-limited |

## Pieces still worth doing later

- Replace MinIO with real S3 + CloudFront / Cloud CDN for media delivery
- Full Postgres HA via CloudNativePG (streaming replicas + automatic failover)
- Outbox pattern for `kafka publish` to make event delivery fully exactly-once
- WebPush for browser notifications (currently only FCM/APNs/web tokens registered)
- Image safety / NSFW classifier on the transcode pipeline
- ABAC / per-room permissions beyond simple membership
- Frontend offline cache for chat history
