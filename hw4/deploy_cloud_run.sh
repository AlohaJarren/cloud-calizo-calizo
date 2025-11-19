#!/usr/bin/env bash
set -euo pipefail

# Usage: bash hw4/deploy_cloud_run.sh <PROJECT_ID> [REGION]
# Example: bash hw4/deploy_cloud_run.sh my-proj us-west1

PROJECT_ID="${1:-}"
REGION="${2:-us-west1}"
REPO="hw4"
IMAGE_TAG="1"

if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: $0 <PROJECT_ID> [REGION]" >&2
  exit 1
fi

echo "[deploy] project: $PROJECT_ID"
echo "[deploy] region : $REGION"

# Enable required services (idempotent)
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com datastore.googleapis.com --project "$PROJECT_ID"

# Create the Artifact Registry repo if missing
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --project "$PROJECT_ID" \
  --description="HW4 repo" || true

IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/hw4:${IMAGE_TAG}"

echo "[build] ${IMAGE_PATH}"
gcloud builds submit --tag "$IMAGE_PATH" --project "$PROJECT_ID"

echo "[deploy] Cloud Run service 'hw4'"
gcloud run deploy hw4 \
  --image "$IMAGE_PATH" \
  --region "$REGION" \
  --allow-unauthenticated \
  --project "$PROJECT_ID"

SERVICE_URL="$(gcloud run services describe hw4 --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
echo "[deploy] url: ${SERVICE_URL}"

# Write URL to hw4/url.txt next to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "${SERVICE_URL}" > "${SCRIPT_DIR}/url.txt"
echo "[deploy] wrote ${SCRIPT_DIR}/url.txt"
