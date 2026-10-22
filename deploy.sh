#!/usr/bin/env bash
# ==============================================================================
# One-Step Auto-Detecting Cloud Run Deployment & IAM Permission Bootstrapper
# Formula E GEN4 35mm Cinema & Interactive AI Kiosk ("Sakura in the Slipstream")
# ==============================================================================
set -euo pipefail

echo "🔍 Auto-detecting Google Cloud Project, Vertex AI Permissions & Active Token..."

# Ensure valid access token from Application Default Credentials if gcloud session needs refresh
ADC_TOKEN="$(python3 -c '
import google.auth, google.auth.transport.requests
try:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    if creds.token:
        print(creds.token)
except Exception:
    pass
' 2>/dev/null || true)"

if [[ -n "${ADC_TOKEN}" ]]; then
  export CLOUDSDK_AUTH_ACCESS_TOKEN="${ADC_TOKEN}"
fi

DETECTED_PROJ="$(PYTHONPATH=./backend python3 -c '
from app.services.gemini_service import detect_runtime_capabilities
print(detect_runtime_capabilities().get("project", ""))
' 2>/dev/null || true)"

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-${DETECTED_PROJ:-$(gcloud config get-value project 2>/dev/null || true)}}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" || "${PROJECT_ID}" == "local-dev-project" ]]; then
  PROJECT_ID="$(gcloud projects list --format='value(projectId)' --limit=1 2>/dev/null || true)"
fi

if [[ -z "${PROJECT_ID}" ]]; then
  echo "❌ Could not auto-detect a GCP Project. Run: export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID"
  exit 1
fi

REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
BUCKET_NAME="${GCS_BUCKET_NAME:-${PROJECT_ID}-fe-kiosk-assets}"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || true)"

echo "✅ Target Project : ${PROJECT_ID} (${PROJECT_NUMBER:-unknown})"
echo "✅ Target Region  : ${REGION}"
echo "✅ Asset Bucket   : gs://${BUCKET_NAME}"

echo "⚙️ Enabling required Vertex AI, Cloud Run, Cloud Tasks, Cloud Build, and Storage APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudtasks.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="${PROJECT_ID}" || true

# Automatically grant Vertex AI, Cloud Tasks & Storage roles to the Cloud Run default SA
if [[ -n "${PROJECT_NUMBER}" ]]; then
  COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  echo "🔐 Ensuring Vertex AI, Cloud Tasks & Storage IAM roles on Cloud Run Service Account (${COMPUTE_SA})..."
  for ROLE in "roles/aiplatform.user" "roles/aiplatform.admin" "roles/storage.admin" "roles/cloudtasks.enqueuer"; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${COMPUTE_SA}" \
      --role="${ROLE}" \
      --quiet >/dev/null 2>&1 || true
  done
fi

echo "⚡ Ensuring Cloud Tasks queue (fe-kiosk-scene-queue) exists in ${REGION}..."
if ! gcloud tasks queues describe fe-kiosk-scene-queue --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud tasks queues create fe-kiosk-scene-queue \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --max-concurrent-dispatches=6 \
    --max-dispatches-per-second=6 >/dev/null 2>&1 || true
fi

echo "🚀 Deploying Unified Formula E GEN4 35mm Cinema & AI Kiosk (fe-kiosk) to Cloud Run..."
gcloud run deploy fe-kiosk \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GCS_BUCKET_NAME=${BUCKET_NAME},CLOUD_TASKS_QUEUE=fe-kiosk-scene-queue,CLOUD_TASKS_LOCATION=${REGION}" \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900

SERVICE_URL="$(gcloud run services describe fe-kiosk --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
gcloud run services update fe-kiosk \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --update-env-vars="SERVICE_URL=${SERVICE_URL}" \
  --quiet >/dev/null 2>&1 || true

echo "=============================================================================="
echo "🏁 Deployment Complete!"
echo "   Live Experience URL : ${SERVICE_URL}"
echo "   Health & Permissions: ${SERVICE_URL}/api/health"
echo "=============================================================================="
