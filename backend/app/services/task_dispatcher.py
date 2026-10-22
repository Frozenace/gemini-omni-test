"""Distributed Cloud Tasks & Parallel `asyncio.gather` Scene Dispatcher.

Automatically distributes the 6-scene Formula E GEN4 35mm pipeline across:
1. **Google Cloud Tasks (`cloudtasks.googleapis.com`)**: When `CLOUD_TASKS_QUEUE` and `SERVICE_URL`
   are configured on Cloud Run and `cloudtasks.tasks.create` permission is present, enqueues 6 HTTP
   worker tasks (`POST /api/tasks/render-scene`) so each scene renders on its own auto-scaled
   Cloud Run instance.
2. **Parallel `asyncio.gather` Fan-Out**: Automatically used for local development or single-container
   deployments, running scenes concurrently with progressive keyframe & 35mm motion-preview updates.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

from app.services.gemini_service import LOCAL_ASSETS_DIR, detect_runtime_capabilities, upload_to_gcs

logger = logging.getLogger(__name__)


def is_cloud_tasks_enabled() -> bool:
    """Return True if Cloud Tasks queue & target Cloud Run service URL are configured and permitted."""
    queue = os.environ.get("CLOUD_TASKS_QUEUE", "").strip()
    service_url = os.environ.get("SERVICE_URL", "").strip()
    if not queue or not service_url:
        return False
    caps = detect_runtime_capabilities()
    perms = caps.get("granted_permissions", [])
    return "cloudtasks.tasks.create" in perms or bool(os.environ.get("FORCE_CLOUD_TASKS"))


def enqueue_scene_cloud_task(
    job_id: str,
    scene_key: str,
    driver_name: str = "Toshiro Sakamoto",
) -> str | None:
    """Enqueue an HTTP task in Google Cloud Tasks targeting `POST /api/tasks/render-scene`."""
    caps = detect_runtime_capabilities()
    project = caps.get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("CLOUD_TASKS_LOCATION", "us-central1")
    queue = os.environ.get("CLOUD_TASKS_QUEUE", "fe-kiosk-scene-queue")
    service_url = os.environ.get("SERVICE_URL", "").rstrip("/")

    if not project or not service_url:
        return None

    try:
        import google.auth
        import google.auth.transport.requests
        import httpx

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)

        parent = f"projects/{project}/locations/{location}/queues/{queue}"
        api_url = f"https://cloudtasks.googleapis.com/v2/{parent}/tasks"

        payload_bytes = json.dumps(
            {
                "job_id": job_id,
                "scene_key": scene_key,
                "driver_name": driver_name,
            }
        ).encode("utf-8")

        task_body: dict[str, Any] = {
            "task": {
                "httpRequest": {
                    "httpMethod": "POST",
                    "url": f"{service_url}/api/tasks/render-scene",
                    "headers": {"Content-Type": "application/json"},
                    "body": base64.b64encode(payload_bytes).decode("utf-8"),
                }
            }
        }

        resp = httpx.post(
            api_url,
            headers={"Authorization": f"Bearer {creds.token}"},
            json=task_body,
            timeout=10.0,
        )
        if resp.status_code in (200, 201):
            task_name = resp.json().get("name", f"{parent}/tasks/{scene_key}")
            logger.info("Enqueued Cloud Task %s for scene=%s", task_name, scene_key)
            return task_name
        logger.warning("Cloud Tasks enqueue returned %s: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Cloud Tasks enqueue failed for scene=%s (falling back to async worker): %s", scene_key, exc)
    return None


def save_distributed_scene_state(job_id: str, scene_key: str, scene_data: dict[str, Any]) -> str:
    """Persist completed scene metadata to local disk and GCS so distributed workers stay synchronized."""
    rel_path = f"jobs/{job_id}/scenes/{scene_key}.json"
    raw_bytes = json.dumps(scene_data, indent=2).encode("utf-8")
    return upload_to_gcs(raw_bytes, rel_path, "application/json")


def load_all_distributed_scenes(job_id: str, expected_keys: list[str]) -> dict[str, dict[str, Any]]:
    """Load completed scene metadata from local disk or GCS across all expected scene keys."""
    found: dict[str, dict[str, Any]] = {}
    for s_key in expected_keys:
        local_file = LOCAL_ASSETS_DIR / f"jobs/{job_id}/scenes/{s_key}.json"
        if local_file.exists():
            try:
                found[s_key] = json.loads(local_file.read_text())
                continue
            except Exception:
                pass
    return found
