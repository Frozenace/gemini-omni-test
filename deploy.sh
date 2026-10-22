#!/usr/bin/env bash
# ==============================================================================
# One-Step Auto-Detecting Cloud Run Deployment & IAM Permission Bootstrapper
# Formula E GEN4 35mm Cinema & Interactive AI Kiosk ("Sakura in the Slipstream")
# ==============================================================================
set -euo pipefail

echo "🔍 Auto-detecting Google Cloud Project & Active Identity..."
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  PROJECT_ID="$(gcloud projects list --format='value(projectId)' --limit=1 2>/dev/null || true)"
fi

if [[ -z "${PROJECT_ID}" ]]; then
  echo "❌ Could not auto-detect a GCP Project. Run: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
BUCKET_NAME="${GCS_BUCKET_NAME:-${PROJECT_ID}-fe-kiosk-assets}"
ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || true)"

echo "✅ Target Project : ${PROJECT_ID} (${PROJECT_NUMBER:-unknown})"
echo "✅ Target Region  : ${REGION}"
echo "✅ Asset Bucket   : gs://${BUCKET_NAME}"
echo "✅ Active Identity: ${ACTIVE_ACCOUNT}"

echo "⚙️ Enabling required Vertex AI, Cloud Run, Cloud Build, and Storage APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="${PROJECT_ID}"

# Automatically attempt to grant Vertex AI & Storage roles to the active user and Cloud Run default SA
# (Succeeds automatically if the caller has Project Owner / IAM Admin permissions; continues gracefully otherwise)
if [[ -n "${PROJECT_NUMBER}" ]]; then
  COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  echo "🔐 Ensuring Vertex AI & Storage IAM roles on Cloud Run Service Account (${COMPUTE_SA})..."
  for ROLE in "roles/aiplatform.user" "roles/aiplatform.admin" "roles/storage.admin"; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${COMPUTE_SA}" \
      --role="${ROLE}" \
      --quiet >/dev/null 2>&1 || true
  done
fi

if [[ -n "${ACTIVE_ACCOUNT}" ]]; then
  MEMBER_PREFIX="user"
  [[ "${ACTIVE_ACCOUNT}" == *"gserviceaccount.com" ]] && MEMBER_PREFIX="serviceAccount"
  for ROLE in "roles/aiplatform.user" "roles/storage.objectAdmin"; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="${MEMBER_PREFIX}:${ACTIVE_ACCOUNT}" \
      --role="${ROLE}" \
      --quiet >/dev/null 2>&1 || true
  done
fi

echo "🪣 Ensuring Cloud Storage bucket gs://${BUCKET_NAME} exists and is publicly readable for kiosk playback..."
if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET_NAME}" --project="${PROJECT_ID}" --location="US"
fi
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="allUsers" \
  --role="roles/storage.objectViewer" >/dev/null 2>&1 || true

echo "🚀 Deploying FastAPI Backend (fe-kiosk-backend) to Cloud Run..."
gcloud run deploy fe-kiosk-backend \
  --source ./backend \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GCS_BUCKET_NAME=${BUCKET_NAME}" \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900

BACKEND_URL="$(gcloud run services describe fe-kiosk-backend --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "✅ Backend deployed at: ${BACKEND_URL}"

echo "🎨 Building & Deploying Liquid Glass Frontend (fe-kiosk-frontend) to Cloud Run..."
gcloud builds submit ./frontend \
  --project "${PROJECT_ID}" \
  --tag "gcr.io/${PROJECT_ID}/fe-kiosk-frontend" \
  --substitutions="_VITE_API_URL=${BACKEND_URL}" || \
docker build -t "gcr.io/${PROJECT_ID}/fe-kiosk-frontend" --build-arg "VITE_API_URL=${BACKEND_URL}" ./frontend

gcloud run deploy fe-kiosk-frontend \
  --image "gcr.io/${PROJECT_ID}/fe-kiosk-frontend" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --port 8080

FRONTEND_URL="$(gcloud run services describe fe-kiosk-frontend --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "=============================================================================="
echo "🏁 Deployment Complete!"
echo "   Frontend Experience : ${FRONTEND_URL}"
echo "   Backend API & Health: ${BACKEND_URL}/api/health"
echo "=============================================================================="
