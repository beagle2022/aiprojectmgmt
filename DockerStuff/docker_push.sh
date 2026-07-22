#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# docker_push.sh — Build, tag, test, and push the AI PM Copilot image
#                  to Docker Hub.
#
# USAGE:
#   chmod +x docker_push.sh
#
#   ./docker_push.sh youruser                    # builds + pushes as youruser/ai-pm-copilot:latest
#   ./docker_push.sh youruser 1.0.1              # also tags :1.0.1
#   ./docker_push.sh youruser 1.0.1 --no-test    # skip smoke test
#   ./docker_push.sh youruser 1.0.1 --no-push    # build + tag only, no push
#
# PREREQUISITES:
#   docker login        (run once before using this script)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Args ──────────────────────────────────────────────────────────────────────
DOCKERHUB_USER="${1:-}"
VERSION="${2:-latest}"
NO_TEST=false
NO_PUSH=false

for arg in "$@"; do
  [[ "$arg" == "--no-test" ]] && NO_TEST=true
  [[ "$arg" == "--no-push" ]] && NO_PUSH=true
done

if [[ -z "$DOCKERHUB_USER" ]]; then
  echo "ERROR: Docker Hub username required."
  echo "Usage: ./docker_push.sh <dockerhub-username> [version] [--no-test] [--no-push]"
  exit 1
fi

IMAGE_NAME="${DOCKERHUB_USER}/ai-pm-copilot"
LOCAL_TAG="ai-pm-copilot:latest"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   AI PM Copilot — Docker Build & Push        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Image     : ${IMAGE_NAME}"
echo "  Version   : ${VERSION}"
echo "  Skip test : ${NO_TEST}"
echo "  Skip push : ${NO_PUSH}"
echo ""

# ── Step 1: Build ─────────────────────────────────────────────────────────────
echo "━━━ [1/4] Building image ━━━━━━━━━━━━━━━━━━━━━━━"
docker build \
  --target production \
  --tag "${LOCAL_TAG}" \
  --label "org.opencontainers.image.title=AI PM Copilot" \
  --label "org.opencontainers.image.description=Agentic AI Project Management Copilot" \
  --label "org.opencontainers.image.version=${VERSION}" \
  --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  .

echo "  ✓ Build complete"
echo ""

# ── Step 2: Smoke test ────────────────────────────────────────────────────────
if [[ "$NO_TEST" == false ]]; then
  echo "━━━ [2/4] Running smoke test ━━━━━━━━━━━━━━━━━━━━"
  docker run --rm \
    "${LOCAL_TAG}" \
    python -c "
from copilot.config import Config
from copilot.memory import MemoryManager
from copilot.orchestrator import Orchestrator
from copilot.agents import AGENT_REGISTRY
from copilot.guardrails import SecurityPipeline
from auth.users import _load_users
from auth.session import validate_session
print('Agents:', list(AGENT_REGISTRY.keys()))
print('Smoke test PASSED')
"
  echo "  ✓ Smoke test passed"
  echo ""
else
  echo "━━━ [2/4] Smoke test SKIPPED ━━━━━━━━━━━━━━━━━━━━"
  echo ""
fi

# ── Step 3: Tag ───────────────────────────────────────────────────────────────
echo "━━━ [3/4] Tagging ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker tag "${LOCAL_TAG}" "${IMAGE_NAME}:latest"
echo "  ✓ Tagged ${IMAGE_NAME}:latest"

if [[ "$VERSION" != "latest" ]]; then
  docker tag "${LOCAL_TAG}" "${IMAGE_NAME}:${VERSION}"
  echo "  ✓ Tagged ${IMAGE_NAME}:${VERSION}"
fi
echo ""

# ── Step 4: Push ──────────────────────────────────────────────────────────────
if [[ "$NO_PUSH" == false ]]; then
  echo "━━━ [4/4] Pushing to Docker Hub ━━━━━━━━━━━━━━━━━"
  docker push "${IMAGE_NAME}:latest"
  echo "  ✓ Pushed :latest"

  if [[ "$VERSION" != "latest" ]]; then
    docker push "${IMAGE_NAME}:${VERSION}"
    echo "  ✓ Pushed :${VERSION}"
  fi
  echo ""
  echo "  ╔══════════════════════════════════════════════╗"
  echo "  ║  Image live on Docker Hub                    ║"
  echo "  ║  docker pull ${IMAGE_NAME}:${VERSION}"
  echo "  ╚══════════════════════════════════════════════╝"
else
  echo "━━━ [4/4] Push SKIPPED (--no-push) ━━━━━━━━━━━━━━"
fi

echo ""
echo "Done."
