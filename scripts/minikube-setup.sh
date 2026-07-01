#!/usr/bin/env bash
# Deploy the social app to a local Minikube cluster.
#
# Prerequisites:
#   brew install minikube kubectl docker
#   minikube start --cpus=4 --memory=6g
#
# Usage:
#   ./scripts/minikube-setup.sh          # full deploy
#   ./scripts/minikube-setup.sh images   # rebuild + reload images only
#   ./scripts/minikube-setup.sh apply    # kubectl apply only (images already loaded)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."
MANIFESTS="$ROOT/k8s/minikube"

# ── helpers ───────────────────────────────────────────────────────────────────
info()  { echo "==> $*"; }
die()   { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" > /dev/null 2>&1 || die "'$1' not found — install it first"
}

wait_for_rollout() {
  local kind="$1" name="$2" ns="${3:-social}"
  info "Waiting for $kind/$name …"
  kubectl rollout status "$kind/$name" -n "$ns" --timeout=120s
}

# ── preflight ─────────────────────────────────────────────────────────────────
require_cmd minikube
require_cmd kubectl
require_cmd docker

if ! minikube status --format='{{.Host}}' 2>/dev/null | grep -q Running; then
  die "Minikube is not running. Start it with: minikube start --cpus=4 --memory=6g"
fi

# ── parse args ────────────────────────────────────────────────────────────────
MODE="${1:-all}"

# ── build + load images ───────────────────────────────────────────────────────
build_and_load_images() {
  info "Building backend image …"
  docker build -t social-backend:latest "$ROOT/backend"

  info "Building frontend image …"
  docker build -t social-frontend:latest "$ROOT/frontend"

  info "Loading images into Minikube (this may take a minute) …"
  minikube image load social-backend:latest
  minikube image load social-frontend:latest
  info "Images loaded."
}

# ── apply manifests ───────────────────────────────────────────────────────────
apply_manifests() {
  info "Enabling Minikube ingress addon …"
  minikube addons enable ingress

  info "Applying manifests …"
  # Apply in numeric order so dependencies exist before consumers
  for f in "$MANIFESTS"/[0-9]*.yaml; do
    info "  kubectl apply -f $(basename "$f")"
    kubectl apply -f "$f"
  done

  # ── wait for stateful services ─────────────────────────────────────────────
  info "Waiting for stateful services to be ready …"
  kubectl rollout status statefulset/postgres  -n social --timeout=120s
  kubectl rollout status statefulset/mongo     -n social --timeout=120s
  kubectl rollout status deployment/redis      -n social --timeout=120s
  kubectl rollout status deployment/kafka      -n social --timeout=120s
  kubectl rollout status deployment/minio      -n social --timeout=120s

  # ── wait for migration job ─────────────────────────────────────────────────
  info "Waiting for DB migration job …"
  kubectl wait --for=condition=complete job/backend-migrate -n social --timeout=120s \
    || kubectl logs -n social -l job-name=backend-migrate --tail=50

  # ── wait for application pods ──────────────────────────────────────────────
  wait_for_rollout deployment backend
  wait_for_rollout deployment events-worker
  wait_for_rollout deployment frontend

  # ── print access info ──────────────────────────────────────────────────────
  MINIKUBE_IP=$(minikube ip)
  echo ""
  echo "======================================================================"
  echo "  Deploy complete!"
  echo ""
  echo "  Run in a separate terminal:  minikube tunnel"
  echo "  Then add to /etc/hosts (use 127.0.0.1 when tunnel is active,"
  echo "  or ${MINIKUBE_IP} without tunnel):"
  echo ""
  echo "    127.0.0.1  api.social.local app.social.local minio.social.local"
  echo ""
  echo "  Frontend :  http://app.social.local"
  echo "  API      :  http://api.social.local"
  echo "  MinIO    :  http://minio.social.local  (admin: minioadmin/minioadmin)"
  echo "  Grafana  :  kubectl port-forward -n social svc/grafana 3000:3000"
  echo "  Jaeger   :  kubectl port-forward -n social svc/jaeger  16686:16686"
  echo "======================================================================"
}

# ── main ──────────────────────────────────────────────────────────────────────
case "$MODE" in
  images) build_and_load_images ;;
  apply)  apply_manifests ;;
  all)
    build_and_load_images
    apply_manifests
    ;;
  *)
    echo "Usage: $0 [all|images|apply]"
    exit 1
    ;;
esac
