"""Main FastAPI Application for Formula E GEN4 35mm Cinema & Interactive AI Kiosk.

Combines:
1. The exact Codelab endpoints (`/api/health`, `/api/process-driver`, `/api/job/{job_id}`)
2. Storyboard & 6-Scene Showcase endpoints (`/api/storyboard`, `/api/generate-full-film`)
3. Driver personalization (`driver_name` parameter replacing Toshiro Sakamoto with the user's own name & photo)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.gemini_service import (
    LOCAL_ASSETS_DIR,
    SCENARIO_SCENES,
    detect_runtime_capabilities,
    generate_driver_avatar,
    generate_driver_prompt,
    generate_formula_e_video,
    upload_to_gcs,
)
from app.services.stitcher import stitch_scenes_with_ending, verify_final_cut

app = FastAPI(title="Formula E GEN4 35mm Cinema & AI Kiosk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve local generated/cached assets at /assets
LOCAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(LOCAL_ASSETS_DIR)), name="assets")

jobs_db: dict[str, dict[str, Any]] = {}
MANIFEST_PATH = LOCAL_ASSETS_DIR / "showcase_manifest.json"


class JobStatus(BaseModel):
    job_id: str
    status: str
    stage: str
    result_url: str | None = None
    avatar_url: str | None = None
    candidates: list[str] | None = None
    judge_verdict: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None


@app.get("/api/health")
def health_check(refresh_permissions: bool = False) -> dict[str, Any]:
    caps = detect_runtime_capabilities(force_refresh=refresh_permissions)
    return {
        "status": "ok",
        "experience": "Formula E Gen4 AI Kiosk",
        "project": caps.get("project"),
        "location": caps.get("location"),
        "auth_mode": caps.get("mode"),
        "supports_interactions": caps.get("supports_interactions"),
        "granted_permissions": caps.get("granted_permissions", []),
    }


@app.get("/api/storyboard")
def get_storyboard() -> dict[str, Any]:
    """Return the 6-scene Toshiro Sakamoto & Momoko storyboard and any pre-rendered assets."""
    manifest: dict[str, Any] = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text())
        except Exception:
            manifest = {}

    scenes_out = []
    for key, meta in SCENARIO_SCENES.items():
        scene_state = manifest.get("scenes", {}).get(key, {})
        scenes_out.append(
            {
                "id": key,
                "title": meta["title"],
                "act": meta["act"],
                "location": meta["location"],
                "image_prompt": meta["image_prompt"].format(driver_name="Toshiro Sakamoto"),
                "video_prompt": meta["video_prompt"].format(driver_name="Toshiro Sakamoto"),
                "candidates": scene_state.get("candidates", []),
                "winner_url": scene_state.get("winner_url"),
                "video_url": scene_state.get("video_url"),
                "judge_verdict": scene_state.get("judge_verdict"),
            }
        )

    return {
        "film_title": "SAKURA IN THE SLIPSTREAM",
        "logline": (
            "Dropped from Formula 2 after family sponsorship ran out, young Japanese driver "
            "Toshiro Sakamoto rebuilds his career in the rainy UK alongside Momoko—returning "
            "home to Tokyo Big Sight in a 600kW Active-AWD Formula E GEN4 machine."
        ),
        "master_video_url": manifest.get("master_video_url"),
        "verification": manifest.get("verification"),
        "scenes": scenes_out,
    }


@app.post("/api/process-driver")
async def process_driver(
    file: UploadFile = File(...),
    option: str = Form("podium_celebration"),
    driver_name: str = Form("Toshiro Sakamoto"),
) -> dict[str, str]:
    """Codelab interactive endpoint: personalize a scene (or replace Toshiro with user photo + name)."""
    job_id = str(uuid.uuid4())
    image_bytes = await file.read()

    clean_name = driver_name.strip() or "Toshiro Sakamoto"
    jobs_db[job_id] = {
        "status": "processing",
        "stage": "generating_prompt",
        "result_url": None,
        "avatar_url": None,
        "candidates": [],
        "judge_verdict": None,
        "verification": None,
    }

    asyncio.create_task(run_kiosk_pipeline(job_id, image_bytes, option, clean_name))
    return {"job_id": job_id, "status": "queued"}


async def run_kiosk_pipeline(
    job_id: str,
    image_bytes: bytes,
    option: str,
    driver_name: str = "Toshiro Sakamoto",
) -> None:
    """Execute the 4-stage Interactions API pipeline in a background worker thread."""
    try:
        jobs_db[job_id]["stage"] = f"Writing 35mm prompt for {driver_name} with Gemini 3.8 Flash..."
        driver_prompt = await asyncio.to_thread(
            generate_driver_prompt, image_bytes, option, driver_name
        )

        jobs_db[job_id]["stage"] = "Rendering 4 Nano Banana 2 keyframes & running Judge..."
        avatar_meta = await asyncio.to_thread(
            generate_driver_avatar,
            driver_prompt,
            image_bytes,
            4,
            True,
        )
        assert isinstance(avatar_meta, dict)
        avatar_bytes = avatar_meta["winner_bytes"]
        winner_interaction_id = avatar_meta["winner_interaction_id"]

        candidate_urls = []
        for c in avatar_meta["candidates"]:
            c_url = await asyncio.to_thread(
                upload_to_gcs,
                c["bytes"],
                f"jobs/{job_id}/candidate_{c['index']}.jpg",
                "image/jpeg",
            )
            candidate_urls.append(c_url)

        winner_url = candidate_urls[avatar_meta["winner_index"]]
        jobs_db[job_id]["avatar_url"] = winner_url
        jobs_db[job_id]["candidates"] = candidate_urls
        jobs_db[job_id]["judge_verdict"] = avatar_meta["judge_verdict"]

        jobs_db[job_id]["stage"] = (
            "Chaining winning keyframe ID into Gemini Omni 1.1 Flash (8s 60fps HD + Audio)..."
        )
        video_bytes = await asyncio.to_thread(
            generate_formula_e_video,
            driver_prompt,
            avatar_bytes,
            winner_interaction_id,
            option,
            driver_name,
        )

        raw_scene_path = LOCAL_ASSETS_DIR / f"jobs/{job_id}/scene_raw.mp4"
        raw_scene_path.parent.mkdir(parents=True, exist_ok=True)
        raw_scene_path.write_bytes(video_bytes)

        jobs_db[job_id]["stage"] = "Appending 35mm finale slate & running verification judge..."
        stitch_res = await asyncio.to_thread(
            stitch_scenes_with_ending,
            [raw_scene_path],
            f"videos/{job_id}.mp4",
            driver_name,
        )
        verification = await asyncio.to_thread(
            verify_final_cut, Path(stitch_res["local_path"]), driver_name
        )

        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["stage"] = "Done"
        jobs_db[job_id]["result_url"] = stitch_res["result_url"]
        jobs_db[job_id]["verification"] = verification
    except Exception as exc:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["stage"] = str(exc)


@app.post("/api/generate-full-film")
async def trigger_full_film(driver_name: str = Form("Toshiro Sakamoto")) -> dict[str, str]:
    """Fan out across all 6 storyboard scenes, stitch with 35mm ending, and verify."""
    job_id = f"film-{uuid.uuid4().hex[:8]}"
    jobs_db[job_id] = {
        "status": "processing",
        "stage": "Initializing 6-scene fan-out pipeline...",
        "result_url": None,
        "avatar_url": None,
        "candidates": [],
        "judge_verdict": None,
        "verification": None,
    }
    asyncio.create_task(run_full_film_pipeline(job_id, driver_name))
    return {"job_id": job_id, "status": "queued"}


async def run_full_film_pipeline(job_id: str, driver_name: str = "Toshiro Sakamoto") -> None:
    """Generate all 6 scenes in parallel/sequence, stitch into the master film, and verify."""
    try:
        scene_keys = list(SCENARIO_SCENES.keys())
        manifest_scenes: dict[str, Any] = {}
        scene_video_paths: list[Path] = []

        for idx, s_key in enumerate(scene_keys, start=1):
            s_title = SCENARIO_SCENES[s_key]["title"]
            jobs_db[job_id]["stage"] = f"[{idx}/6] {s_title}: Gemini 3.8 Flash prompt & 4 Nano Banana keyframes..."
            prompt = await asyncio.to_thread(generate_driver_prompt, None, s_key, driver_name)
            avatar_meta = await asyncio.to_thread(generate_driver_avatar, prompt, None, 4, True)
            assert isinstance(avatar_meta, dict)

            c_urls = []
            for c in avatar_meta["candidates"]:
                url = await asyncio.to_thread(
                    upload_to_gcs,
                    c["bytes"],
                    f"scenes/{s_key}/candidate_{c['index']}.jpg",
                    "image/jpeg",
                )
                c_urls.append(url)

            winner_url = c_urls[avatar_meta["winner_index"]]
            jobs_db[job_id]["stage"] = f"[{idx}/6] {s_title}: Chaining Gemini Omni 1.1 Flash 8s 60fps video..."
            v_bytes = await asyncio.to_thread(
                generate_formula_e_video,
                prompt,
                avatar_meta["winner_bytes"],
                avatar_meta["winner_interaction_id"],
                s_key,
                driver_name,
            )
            v_url = await asyncio.to_thread(
                upload_to_gcs,
                v_bytes,
                f"scenes/{s_key}/scene.mp4",
                "video/mp4",
            )
            local_v_path = LOCAL_ASSETS_DIR / f"scenes/{s_key}/scene.mp4"
            scene_video_paths.append(local_v_path)

            manifest_scenes[s_key] = {
                "candidates": c_urls,
                "winner_url": winner_url,
                "video_url": v_url,
                "judge_verdict": avatar_meta["judge_verdict"],
            }

        jobs_db[job_id]["stage"] = "Stitching all 6 scenes + 35mm finale slate via FFmpeg..."
        stitch_res = await asyncio.to_thread(
            stitch_scenes_with_ending,
            scene_video_paths,
            "final/toshiro_sakura_master_35mm.mp4",
            driver_name,
        )

        jobs_db[job_id]["stage"] = "Running Final Cut Multimodal Verification Judge..."
        verification = await asyncio.to_thread(
            verify_final_cut, Path(stitch_res["local_path"]), driver_name
        )

        manifest_data = {
            "driver_name": driver_name,
            "master_video_url": stitch_res["result_url"],
            "verification": verification,
            "scenes": manifest_scenes,
        }
        MANIFEST_PATH.write_text(json.dumps(manifest_data, indent=2))

        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["stage"] = "Done"
        jobs_db[job_id]["result_url"] = stitch_res["result_url"]
        jobs_db[job_id]["verification"] = verification
    except Exception as exc:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["stage"] = str(exc)


@app.get("/api/job/{job_id}", response_model=JobStatus)
def get_job_status(job_id: str) -> JobStatus:
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    data = jobs_db[job_id]
    return JobStatus(
        job_id=job_id,
        status=data["status"],
        stage=data["stage"],
        result_url=data.get("result_url"),
        avatar_url=data.get("avatar_url"),
        candidates=data.get("candidates"),
        judge_verdict=data.get("judge_verdict"),
        verification=data.get("verification"),
    )
