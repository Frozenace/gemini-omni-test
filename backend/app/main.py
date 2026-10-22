"""Main FastAPI Application for Formula E GEN4 35mm Cinema & Interactive AI Kiosk.

Combines:
1. The exact Codelab endpoints (`/api/health`, `/api/process-driver`, `/api/job/{job_id}`)
2. Storyboard & 6-Scene Showcase endpoints (`/api/storyboard`, `/api/generate-full-film`)
3. Cloud Tasks distributed worker endpoint (`POST /api/tasks/render-scene`) + `asyncio.gather` parallel fan-out
4. Instant 35mm motion previews (`preview_video_url`) & progressive candidate streaming (`on_candidate_ready`)
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
    render_fast_35mm_preview,
    upload_to_gcs,
)
from app.services.stitcher import stitch_scenes_with_ending, verify_final_cut
from app.services.task_dispatcher import (
    enqueue_scene_cloud_task,
    is_cloud_tasks_enabled,
    load_all_distributed_scenes,
    save_distributed_scene_state,
)

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
_MANIFEST_LOCK = asyncio.Lock()


class JobStatus(BaseModel):
    job_id: str
    status: str
    stage: str
    progress_pct: int = 0
    result_url: str | None = None
    preview_video_url: str | None = None
    avatar_url: str | None = None
    candidates: list[str] | None = None
    judge_verdict: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    scenes_progress: dict[str, str] | None = None
    execution_mode: str | None = None


class SceneTaskPayload(BaseModel):
    job_id: str
    scene_key: str
    driver_name: str = "Toshiro Sakamoto"


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
        "cloud_tasks_enabled": is_cloud_tasks_enabled(),
        "granted_permissions": caps.get("granted_permissions", []),
    }


async def _update_manifest_scene(scene_key: str, scene_entry: dict[str, Any], driver_name: str) -> None:
    """Incrementally update `showcase_manifest.json` so the frontend storyboard updates in real time."""
    async with _MANIFEST_LOCK:
        manifest: dict[str, Any] = {}
        if MANIFEST_PATH.exists():
            try:
                manifest = json.loads(MANIFEST_PATH.read_text())
            except Exception:
                manifest = {}
        manifest.setdefault("driver_name", driver_name)
        manifest.setdefault("scenes", {})[scene_key] = scene_entry
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


@app.get("/api/storyboard")
def get_storyboard() -> dict[str, Any]:
    """Return the 6-scene Toshiro Sakamoto & Momoko storyboard and any pre-rendered or streaming assets."""
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
                "preview_video_url": scene_state.get("preview_video_url"),
                "video_url": scene_state.get("video_url"),
                "judge_verdict": scene_state.get("judge_verdict"),
                "status": scene_state.get("status", "ready" if scene_state.get("video_url") else "idle"),
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
        "stage": "Directing 35mm prompt with Gemini 3.8 Flash...",
        "progress_pct": 8,
        "result_url": None,
        "preview_video_url": None,
        "avatar_url": None,
        "candidates": [],
        "judge_verdict": None,
        "verification": None,
        "scenes_progress": {option: "prompting"},
        "execution_mode": "interactive_stream",
    }

    asyncio.create_task(run_kiosk_pipeline(job_id, image_bytes, option, clean_name))
    return {"job_id": job_id, "status": "queued"}


async def run_kiosk_pipeline(
    job_id: str,
    image_bytes: bytes,
    option: str,
    driver_name: str = "Toshiro Sakamoto",
) -> None:
    """Execute the 4-stage Interactions API pipeline with progressive keyframe streaming & instant 35mm motion preview."""
    try:
        jobs_db[job_id]["stage"] = f"Writing 35mm prompt for {driver_name} with Gemini 3.8 Flash..."
        jobs_db[job_id]["progress_pct"] = 12
        driver_prompt = await asyncio.to_thread(
            generate_driver_prompt, image_bytes, option, driver_name
        )

        jobs_db[job_id]["stage"] = "Rendering 4 Nano Banana 2 keyframes in parallel (4x concurrent)..."
        jobs_db[job_id]["progress_pct"] = 25
        jobs_db[job_id]["scenes_progress"] = {option: "keyframes"}

        streamed_urls: dict[int, str] = {}

        def _on_candidate(c_idx: int, c_bytes: bytes) -> None:
            url = upload_to_gcs(
                c_bytes,
                f"jobs/{job_id}/candidate_{c_idx}.jpg",
                "image/jpeg",
            )
            streamed_urls[c_idx] = url
            ordered = [streamed_urls[k] for k in sorted(streamed_urls.keys())]
            jobs_db[job_id]["candidates"] = ordered
            if not jobs_db[job_id].get("avatar_url"):
                jobs_db[job_id]["avatar_url"] = url
            jobs_db[job_id]["progress_pct"] = min(50, 25 + len(ordered) * 6)
            jobs_db[job_id]["stage"] = f"Streamed {len(ordered)}/4 Nano Banana 35mm keyframes..."

        avatar_meta = await asyncio.to_thread(
            generate_driver_avatar,
            driver_prompt,
            image_bytes,
            4,
            True,
            _on_candidate,
        )
        assert isinstance(avatar_meta, dict)
        avatar_bytes = avatar_meta["winner_bytes"]
        winner_interaction_id = avatar_meta["winner_interaction_id"]

        candidate_urls = [
            streamed_urls.get(c["index"])
            or await asyncio.to_thread(
                upload_to_gcs,
                c["bytes"],
                f"jobs/{job_id}/candidate_{c['index']}.jpg",
                "image/jpeg",
            )
            for c in avatar_meta["candidates"]
        ]
        winner_url = candidate_urls[avatar_meta["winner_index"]]
        jobs_db[job_id]["avatar_url"] = winner_url
        jobs_db[job_id]["candidates"] = candidate_urls
        jobs_db[job_id]["judge_verdict"] = avatar_meta["judge_verdict"]
        jobs_db[job_id]["progress_pct"] = 58

        # Immediately generate a <1s 35mm motion preview so the UI shows live video movement right away
        jobs_db[job_id]["stage"] = "Streaming live 35mm motion preview while Gemini Omni renders 60fps HD..."
        try:
            preview_bytes = await asyncio.to_thread(render_fast_35mm_preview, avatar_bytes, 4)
            preview_url = await asyncio.to_thread(
                upload_to_gcs,
                preview_bytes,
                f"jobs/{job_id}/preview_35mm.mp4",
                "video/mp4",
            )
            jobs_db[job_id]["preview_video_url"] = preview_url
        except Exception:
            pass

        jobs_db[job_id]["stage"] = (
            "Chaining winning keyframe ID into Gemini Omni 1.1 Flash (8s 60fps HD + Audio)..."
        )
        jobs_db[job_id]["progress_pct"] = 68
        jobs_db[job_id]["scenes_progress"] = {option: "video"}

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
        jobs_db[job_id]["progress_pct"] = 88
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
        jobs_db[job_id]["progress_pct"] = 100
        jobs_db[job_id]["result_url"] = stitch_res["result_url"]
        jobs_db[job_id]["verification"] = verification
        jobs_db[job_id]["scenes_progress"] = {option: "completed"}
    except Exception as exc:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["stage"] = str(exc)


async def _render_single_scene_worker(
    job_id: str,
    s_key: str,
    driver_name: str,
    sem: asyncio.Semaphore | None = None,
) -> dict[str, Any]:
    """Render a single storyboard scene (4 parallel keyframes + fast 35mm preview + Gemini Omni 8s 60fps clip)."""
    async def _run() -> dict[str, Any]:
        if job_id in jobs_db and jobs_db[job_id].get("scenes_progress") is not None:
            jobs_db[job_id]["scenes_progress"][s_key] = "prompting"

        prompt = await asyncio.to_thread(generate_driver_prompt, None, s_key, driver_name)

        if job_id in jobs_db and jobs_db[job_id].get("scenes_progress") is not None:
            jobs_db[job_id]["scenes_progress"][s_key] = "keyframes (4x parallel)"

        streamed_urls: dict[int, str] = {}

        def _on_cand(c_idx: int, c_bytes: bytes) -> None:
            url = upload_to_gcs(
                c_bytes,
                f"scenes/{s_key}/candidate_{c_idx}.jpg",
                "image/jpeg",
            )
            streamed_urls[c_idx] = url
            if job_id in jobs_db and not jobs_db[job_id].get("avatar_url"):
                jobs_db[job_id]["avatar_url"] = url

        avatar_meta = await asyncio.to_thread(
            generate_driver_avatar, prompt, None, 4, True, _on_cand
        )
        assert isinstance(avatar_meta, dict)

        c_urls = [
            streamed_urls.get(c["index"])
            or await asyncio.to_thread(
                upload_to_gcs,
                c["bytes"],
                f"scenes/{s_key}/candidate_{c['index']}.jpg",
                "image/jpeg",
            )
            for c in avatar_meta["candidates"]
        ]
        winner_url = c_urls[avatar_meta["winner_index"]]

        # Immediately produce a fast 35mm motion preview so the storyboard scene card moves right away
        preview_url = None
        try:
            p_bytes = await asyncio.to_thread(
                render_fast_35mm_preview, avatar_meta["winner_bytes"], 4
            )
            preview_url = await asyncio.to_thread(
                upload_to_gcs,
                p_bytes,
                f"scenes/{s_key}/preview_35mm.mp4",
                "video/mp4",
            )
            if job_id in jobs_db and not jobs_db[job_id].get("preview_video_url"):
                jobs_db[job_id]["preview_video_url"] = preview_url
        except Exception:
            pass

        await _update_manifest_scene(
            s_key,
            {
                "candidates": c_urls,
                "winner_url": winner_url,
                "preview_video_url": preview_url,
                "video_url": None,
                "judge_verdict": avatar_meta["judge_verdict"],
                "status": "rendering_video",
            },
            driver_name,
        )

        if job_id in jobs_db and jobs_db[job_id].get("scenes_progress") is not None:
            jobs_db[job_id]["scenes_progress"][s_key] = "omni_60fps_video"

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

        scene_entry = {
            "scene_key": s_key,
            "candidates": c_urls,
            "winner_url": winner_url,
            "preview_video_url": preview_url,
            "video_url": v_url,
            "local_video_path": str(local_v_path),
            "judge_verdict": avatar_meta["judge_verdict"],
            "status": "ready",
        }
        await _update_manifest_scene(s_key, scene_entry, driver_name)
        await asyncio.to_thread(save_distributed_scene_state, job_id, s_key, scene_entry)

        if job_id in jobs_db and jobs_db[job_id].get("scenes_progress") is not None:
            jobs_db[job_id]["scenes_progress"][s_key] = "completed"
            done_count = sum(
                1 for v in jobs_db[job_id]["scenes_progress"].values() if v == "completed"
            )
            jobs_db[job_id]["progress_pct"] = min(85, 10 + int((done_count / 6) * 75))
            jobs_db[job_id]["stage"] = f"Completed {done_count}/6 scenes in parallel..."

        return scene_entry

    if sem is not None:
        async with sem:
            return await _run()
    return await _run()


@app.post("/api/tasks/render-scene")
async def cloud_task_render_scene(payload: SceneTaskPayload) -> dict[str, Any]:
    """Google Cloud Tasks HTTP Worker endpoint: renders a single scene on a dedicated Cloud Run instance."""
    if payload.scene_key not in SCENARIO_SCENES:
        raise HTTPException(status_code=400, detail=f"Unknown scene_key: {payload.scene_key}")
    scene_entry = await _render_single_scene_worker(
        payload.job_id, payload.scene_key, payload.driver_name, sem=None
    )
    return {"status": "completed", "scene_key": payload.scene_key, "video_url": scene_entry["video_url"]}


@app.post("/api/generate-full-film")
async def trigger_full_film(driver_name: str = Form("Toshiro Sakamoto")) -> dict[str, str]:
    """Fan out across all 6 storyboard scenes (via Cloud Tasks or parallel asyncio), stitch with 35mm ending, and verify."""
    job_id = f"film-{uuid.uuid4().hex[:8]}"
    mode = "cloud_tasks" if is_cloud_tasks_enabled() else "parallel_asyncio"
    jobs_db[job_id] = {
        "status": "processing",
        "stage": f"Dispatching 6 scenes in parallel ({mode})...",
        "progress_pct": 5,
        "result_url": None,
        "preview_video_url": None,
        "avatar_url": None,
        "candidates": [],
        "judge_verdict": None,
        "verification": None,
        "scenes_progress": {k: "queued" for k in SCENARIO_SCENES},
        "execution_mode": mode,
    }
    asyncio.create_task(run_full_film_pipeline(job_id, driver_name))
    return {"job_id": job_id, "status": "queued", "execution_mode": mode}


async def run_full_film_pipeline(job_id: str, driver_name: str = "Toshiro Sakamoto") -> None:
    """Distribute all 6 scenes via Cloud Tasks (or parallel asyncio.gather), stitch master film, and verify."""
    try:
        scene_keys = list(SCENARIO_SCENES.keys())
        manifest_scenes: dict[str, Any] = {}

        if is_cloud_tasks_enabled():
            jobs_db[job_id]["stage"] = "Enqueuing 6 distributed scene workers to Google Cloud Tasks..."
            fallback_keys: list[str] = []
            for s_key in scene_keys:
                task_name = await asyncio.to_thread(
                    enqueue_scene_cloud_task, job_id, s_key, driver_name
                )
                if task_name:
                    jobs_db[job_id]["scenes_progress"][s_key] = "cloud_task_dispatched"
                else:
                    fallback_keys.append(s_key)

            # Run any scenes that couldn't enqueue in-process concurrently
            sem = asyncio.Semaphore(3)
            fallback_tasks = [
                asyncio.create_task(_render_single_scene_worker(job_id, k, driver_name, sem))
                for k in fallback_keys
            ]

            # Poll distributed scene state until all 6 scenes complete
            for _ in range(180):
                completed_map = await asyncio.to_thread(
                    load_all_distributed_scenes, job_id, scene_keys
                )
                for k in completed_map:
                    jobs_db[job_id]["scenes_progress"][k] = "completed"
                done_cnt = len(completed_map)
                jobs_db[job_id]["progress_pct"] = min(85, 10 + int((done_cnt / 6) * 75))
                if done_cnt == len(scene_keys):
                    manifest_scenes = completed_map
                    break
                await asyncio.sleep(3)

            if fallback_tasks:
                await asyncio.gather(*fallback_tasks)
                manifest_scenes = await asyncio.to_thread(
                    load_all_distributed_scenes, job_id, scene_keys
                )
        else:
            # Parallel in-process fan-out across scenes with Semaphore(3) (12 concurrent image threads max)
            sem = asyncio.Semaphore(3)
            jobs_db[job_id]["stage"] = (
                "Fanning out 6 scenes in parallel (4x concurrent Nano Banana keyframes + live 35mm previews)..."
            )
            results = await asyncio.gather(
                *[_render_single_scene_worker(job_id, s_key, driver_name, sem) for s_key in scene_keys]
            )
            for entry in results:
                manifest_scenes[entry["scene_key"]] = entry

        scene_video_paths = [
            Path(manifest_scenes[k].get("local_video_path") or (LOCAL_ASSETS_DIR / f"scenes/{k}/scene.mp4"))
            for k in scene_keys
        ]

        jobs_db[job_id]["stage"] = "Stitching all 6 scenes + 35mm finale slate via FFmpeg..."
        jobs_db[job_id]["progress_pct"] = 90
        stitch_res = await asyncio.to_thread(
            stitch_scenes_with_ending,
            scene_video_paths,
            "final/toshiro_sakura_master_35mm.mp4",
            driver_name,
        )

        jobs_db[job_id]["stage"] = "Running Final Cut Multimodal Verification Judge..."
        jobs_db[job_id]["progress_pct"] = 96
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
        jobs_db[job_id]["progress_pct"] = 100
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
        progress_pct=data.get("progress_pct", 0),
        result_url=data.get("result_url"),
        preview_video_url=data.get("preview_video_url"),
        avatar_url=data.get("avatar_url"),
        candidates=data.get("candidates"),
        judge_verdict=data.get("judge_verdict"),
        verification=data.get("verification"),
        scenes_progress=data.get("scenes_progress"),
        execution_mode=data.get("execution_mode"),
    )
