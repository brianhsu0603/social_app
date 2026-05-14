# Social App

A Facebook-style social network: posts (text/image/video), likes, comments, friends, a personalized feed, and real-time 1:1 and group chat.

## Architecture

```
                            ┌─────────────┐
            HTTPS / WSS     │  Frontend   │  (React + Vite + Tailwind, served by nginx)
        ┌──────────────────►│   :80/:443  │
        │                   └─────────────┘
        │
   ┌────┴────┐  REST + WebSocket
   │ Ingress │◄──────────────────────────┐
   └────┬────┘                           │
        │                                │
        │                   ┌────────────┴────────────┐
        ▼                   │       Backend (FastAPI) │
                            │      2+ replicas, HPA   │
                            └──┬─────┬──────┬─────┬───┘
                               │     │      │     │
                Postgres ◄─────┘     │      │     └───► MinIO (media, S3 API)
                (users, posts,       │      │
                 likes, comments,    │      └────► MongoDB (chat messages, durable history)
                 friends, rooms)     │
                                     └────► Kafka ─┐
                                                   │ chat.messages (per-room fan-out)
                                                   │ social.events (post.created, etc.)
                                                   │
                                            ┌──────┴────────┐
                                            │ Events worker │  (separate deployment)
                                            └───────────────┘
                Redis ◄── friend-id cache, future presence/pub-sub
```

### Chat data flow

1. Client opens `WSS /chat/ws/{room_id}?token=…`.
2. Server validates membership, accepts the socket, registers it in a per-pod registry.
3. Sender publishes a frame → backend persists to MongoDB → publishes to Kafka `chat.messages` keyed by `room_id`.
4. Every backend pod runs a consumer group with a unique name, so each pod receives every message and pushes it to whatever sockets it owns. This is how horizontal scaling stays consistent without sticky sessions.

### Why these pieces

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI | Async, fast, native WebSockets, Pydantic validation |
| Relational data | Postgres + SQLAlchemy + Alembic | Strongly-typed schema for users / posts / graph |
| Chat history | MongoDB | Append-heavy, document-shaped, schema flexibility |
| Cache / hot lookups | Redis | Friend-ID cache today, presence/rate-limit later |
| Event bus | Kafka | Durable per-room ordering for chat, event log for analytics |
| Object storage | MinIO | S3-compatible API; swap to AWS S3 in prod with no code change |
| Frontend | React + Vite + React Query + Tailwind | Fast iteration, sensible defaults |
| Container orchestration | Kubernetes | HPA, rolling updates, declarative infra |
| CI/CD | GitHub Actions | Free, integrated, builds + pushes to GHCR + deploys via kubectl |

## Project layout

```
backend/        FastAPI service, workers, Alembic migrations, tests
frontend/       React app (Vite, Tailwind, React Query)
k8s/            Kubernetes manifests (namespace, deps, app, ingress)
.github/        CI/CD workflows
docker-compose.yml   Local dev stack (one command to boot everything)
.env.example
```

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

Then visit:

- App:        http://localhost:5173
- API docs:   http://localhost:8000/docs
- MinIO UI:   http://localhost:9001 (login: `minioadmin` / `minioadmin`)

Migrations run automatically when the backend container starts (see the `command:` block in `docker-compose.yml`). To run them manually:

```bash
docker compose run --rm backend alembic upgrade head
```

To create new migrations after model changes:

```bash
docker compose run --rm backend alembic revision --autogenerate -m "your message"
```

## Run tests

```bash
docker compose run --rm backend pytest
# or, locally with venv:
cd backend && pip install -r requirements.txt && pytest
```

## Deploy to Kubernetes

The manifests assume an ingress controller (nginx-ingress) and a default StorageClass.

```bash
# Set image registry once
export REG=ghcr.io/your-org

# Build & push (CI does this automatically on push to main)
docker build -t $REG/social-backend:latest ./backend && docker push $REG/social-backend:latest
docker build -t $REG/social-frontend:latest \
  --build-arg VITE_API_URL=https://api.example.com \
  --build-arg VITE_WS_URL=wss://api.example.com \
  ./frontend && docker push $REG/social-frontend:latest

# Apply
kubectl apply -f k8s/
kubectl -n social get pods
```

Update DNS so `api.example.com` and `app.example.com` point to your ingress IP, then change `MINIO_PUBLIC_ENDPOINT` in `k8s/10-config.yaml` to the public MinIO URL (or swap MinIO for S3).

## CI/CD

- `backend-ci.yml`: runs pytest on PRs and pushes; on `main`, builds and pushes a Docker image to GHCR.
- `frontend-ci.yml`: runs typecheck + build; pushes nginx-served SPA image to GHCR on `main`.
- `deploy.yml`: triggers on successful CI runs, applies `k8s/` and rolls deployments.

Required repo secrets:
- `KUBECONFIG` — base64-encoded kubeconfig for the target cluster.

## API surface (quick reference)

| Method | Path | What |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | JWT auth |
| GET | `/auth/me` | Current user |
| GET | `/users/search?q=…`, `/users/{id}` | User lookup |
| PATCH | `/users/me` | Update profile |
| POST/GET/DELETE | `/posts`, `/posts/{id}`, `/posts/user/{id}` | Posts |
| POST/DELETE | `/posts/{id}/like` | Like / unlike |
| GET/POST/DELETE | `/posts/{id}/comments`, `/comments/{id}` | Comments |
| GET | `/feed` | Friend timeline |
| POST/GET/DELETE | `/friends/requests/...`, `/friends` | Friend graph |
| POST | `/media/upload` | Image / video upload to MinIO |
| POST/GET | `/chat/rooms`, `/chat/rooms/{id}/messages` | Rooms + REST send |
| WS | `/chat/ws/{room_id}?token=…` | Live chat |

## What's deliberately out of scope (good follow-ups)

- Presence indicators / typing events (Redis pub/sub)
- Push notifications (events worker → APNs/FCM)
- Read receipts (Mongo `reads` collection)
- Image transcoding pipeline (Kafka → ffmpeg worker → MinIO)
- Refresh tokens + token rotation
- Rate limiting and abuse protection
- Search (Postgres full-text → Meilisearch / OpenSearch)
- Observability (Prometheus + Grafana, OpenTelemetry traces)
- A real Kafka cluster (Strimzi operator or MSK/Confluent)
