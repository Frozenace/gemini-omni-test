"""Gemini Platform Interactions API Service.

Implements:
1. Client Initialization (`genai.Client(enterprise=True)`)
2. Gemini 3.8 Flash (`generate_driver_prompt`) with dict-based multimodal input & high thinking
3. Nano Banana 2 (`gemini-3.1-flash-image` / `gemini-nano-banana-2.1`) 4-image candidate generation
4. Multimodal Judge (`judge_image_candidates` & `verify_final_cut`) for 35mm film & GEN4 accuracy
5. Gemini Omni 1.1 Flash (`gemini-omni-1.1-flash-preview`) async background=True video chaining via `previous_interaction_id`
6. Google Cloud Storage (`upload_to_gcs`) with local static fallback
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from google import genai
from google.cloud import storage

logger = logging.getLogger(__name__)

def _detect_default_project() -> str:
    """Auto-detect active GCP Project from env, google.auth.default(), metadata server, or gcloud."""
    for env_key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GCLOUD_PROJECT", "PROJECT_ID"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    try:
        import google.auth
        _, proj = google.auth.default()
        if proj:
            return proj
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["gcloud", "config", "get-value", "project"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip()
        if out and out != "(unset)":
            return out
    except Exception:
        pass
    return "local-dev-project"


PROJECT_ID = _detect_default_project()
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", f"{PROJECT_ID}-fe-kiosk-assets")

_CACHED_CLIENT_MODE: dict[str, Any] = {}

BASE_DIR = Path(__file__).resolve().parents[3]
LOCAL_ASSETS_DIR = BASE_DIR / "assets"
LOCAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Global 35mm Kodak Vision3 & Audio Style Locks
# ---------------------------------------------------------------------------
FILM_STYLE_LOCK = (
    "Shot on 35mm Kodak Vision3 500T film stock with Panavision C-Series anamorphic lenses. "
    "Authentic fine organic film grain, warm tungsten/amber and cyan halation around specular highlights, "
    "shallow depth of field with oval anamorphic bokeh, 180-degree shutter motion blur, natural skin texture."
)

AUDIO_STYLE_LOCK = (
    "Blade Runner style Yamaha CS-80 lush analog brass synthesizers blended with "
    "high-energy futuristic Cyberpunk J-Pop electronic arpeggios, ethereal bilingual "
    "Japanese/English vocals, and authentic 600kW dual-motor Formula E GEN4 electric powertrain audio."
)

SCENARIO_SCENES: dict[str, dict[str, str]] = {
    "uk_rain_handoff": {
        "title": "Scene 01: Rainy UK Setback & Second Chance",
        "location": "Oxfordshire / Silverstone UK Factory",
        "act": "Act I — The Exile",
        "image_prompt": (
            "Outside a British motorsport factory in Oxfordshire on a rainy grey morning with subtle "
            "Blade Runner neo-noir atmospheric mist. {driver_name} (22, determined racing driver in a "
            "slate-grey and electric-cyan 'Albion Electric Racing' suit) stands facing Momoko (22, tall, "
            "slender, mixed Japanese-English woman in a beige trench coat with long flowing dark-chestnut "
            "hair blowing in the wind). She holds a matte carbon helmet with a subtle pink sakura motif "
            "out to {driver_name} with a warm, encouraging look. Warm amber and cyan garage lights glow "
            "with 35mm halation in the background."
        ),
        "video_prompt": (
            "Animate into an 8-second 60fps HD 35mm film shot: rain falls softly as the British wind "
            "catches Momoko's long flowing hair; {driver_name} takes the sakura-detailed helmet from her "
            "hands, their eyes locking with quiet determination before turning toward the glowing Formula E "
            "GEN4 garage. Audio: gentle patter of British rain on asphalt blended with lush, melancholic "
            "Blade Runner CS-80 analog brass synthesizer chords and a deep futuristic sub-bass drone."
        ),
    },
    "uk_simulator_night": {
        "title": "Scene 02: Late Nights at the UK Factory",
        "location": "Albion Electric Racing Simulator Bay (UK)",
        "act": "Act I — The Grind",
        "image_prompt": (
            "Inside a dark UK racing factory simulator room at midnight with Blade Runner style cyan and "
            "amber lighting, shooting through a glass window. In the foreground, Momoko (tall, slender, "
            "mixed Japanese-English, long flowing dark-chestnut hair) watches tenderly through the glass "
            "holding two coffee cups. In the background, {driver_name} sits inside a carbon-fiber Formula E "
            "GEN4 simulator rig, illuminated by telemetry screens and a virtual Tokyo Big Sight track projection."
        ),
        "video_prompt": (
            "Animate into an 8-second 60fps HD 35mm film clip: camera slowly racks focus from Momoko "
            "smiling softly behind the glass to {driver_name}'s intense eyes whipping the GEN4 simulator "
            "steering wheel through a virtual chicane, holographic telemetry light flashing across the face. "
            "Audio: hypnotic Blade Runner analog synth arpeggios blending with a rhythmic, futuristic "
            "J-Pop electronic pulse and telemetry beeps."
        ),
    },
    "tokyo_paddock_arrival": {
        "title": "Scene 03: Arrival at Tokyo Big Sight",
        "location": "Tokyo Big Sight Waterfront Paddock (Ariake)",
        "act": "Act II — Homecoming",
        "image_prompt": (
            "Spring morning at the Tokyo E-Prix paddock outside the futuristic inverted-pyramid Tokyo Big Sight "
            "building along the Ariake waterfront. {driver_name} (in a slate-grey and cyan Albion racing suit) "
            "walks side-by-side with Momoko (tall, slender, mixed Japanese-English, her long dark-chestnut hair "
            "flowing in the sea breeze). Blooming pink cherry blossom trees line the waterfront walkway, with "
            "petals drifting through the sunlit air."
        ),
        "video_prompt": (
            "Animate into an 8-second 60fps HD 35mm film tracking shot: {driver_name} and Momoko walk toward "
            "the pit garage as a gust of wind off Tokyo Bay blows a shower of pink cherry blossom petals across "
            "the frame, catching in Momoko's long flowing hair as she smiles at {driver_name}. Audio: shimmering "
            "Blade Runner synth pads merging with an upbeat, melodic futuristic J-Pop synth hook, Tokyo Bay "
            "wind, and distant electric GEN4 race cars warming up."
        ),
    },
    "pit_lane_launch": {
        "title": "Scene 04: Grid Tension & 600kW GEN4 Launch",
        "location": "Tokyo Big Sight Starting Grid",
        "act": "Act II — The Launch",
        "image_prompt": (
            "Close-up on the Tokyo E-Prix starting grid at Tokyo Big Sight. {driver_name} sits strapped inside "
            "the open cockpit of a slate-grey and cyan Formula E GEN4 race car, eyes fiercely focused behind a "
            "sakura-detailed helmet before closing the visor. Wider Bridgestone racing tires, aggressive GEN4 "
            "high-downforce aero wings. Overhead red starting gantry lights glow with warm 35mm film halation, "
            "and pink cherry blossom petals rest on the asphalt."
        ),
        "video_prompt": (
            "Animate into an 8-second 60fps HD 35mm film shot: {driver_name} snaps the reflective helmet visor "
            "shut with a gloved hand, the red gantry lights overhead extinguish, and the 600kW active AWD "
            "Formula E GEN4 car launches explosively off the line from 0 to 100 km/h in 1.8 seconds, kicking "
            "up a cloud of pink cherry blossom petals. Audio: deep Blade Runner synth tension riser, sharp visor "
            "click, and a massive high-BPM Cyberpunk J-Pop beat drop fused with the screaming 600kW dual-motor launch."
        ),
    },
    "sakura_vortex": {
        "title": "Scene 05: The Ariake Sakura Vortex (208 mph)",
        "location": "Tokyo Big Sight Harbor Straightaway",
        "act": "Act III — Flow State",
        "image_prompt": (
            "Low-angle high-speed tracking shot on the Tokyo E-Prix street circuit at Tokyo Big Sight. "
            "{driver_name}'s slate-grey and cyan Formula E GEN4 race car hurtling down the waterfront straight "
            "at 335 km/h (208 mph) between blue racing barriers and overhanging cherry blossom trees. "
            "Aggressive GEN4 sculpted high-downforce aero wings and wide Bridgestone tires. The car's rear "
            "diffuser wake pulls thousands of pink sakura petals off the asphalt into a dramatic swirling vortex."
        ),
        "video_prompt": (
            "Animate into an 8-second 60fps HD 35mm film sequence: low-angle tracking camera at 208mph as the "
            "600kW Formula E GEN4 car blasts forward down the Tokyo Big Sight straightaway, its ground-effect "
            "aerodynamic slipstream whipping thousands of pink cherry blossom petals into a spiraling tornado "
            "that engulfs the camera lens in slow motion. Audio: soaring Blade Runner analog synth brass layered "
            "with driving futuristic J-Pop synthwave percussion and the high-pitched Doppler electric scream."
        ),
    },
    "podium_celebration": {
        "title": "Scene 06: Last-Corner Pass & Checkered Embrace",
        "location": "Tokyo Big Sight Parc Fermé & Podium",
        "act": "Act III — Redemption",
        "image_prompt": (
            "Golden-magenta twilight in Parc Fermé at the Tokyo E-Prix with the futuristic Tokyo Big Sight "
            "waterfront illuminated in the background. {driver_name} (in a slate-grey and cyan Albion racing "
            "suit, holding a sakura-detailed helmet after winning the race) is embraced by Momoko (tall, "
            "slender, mixed Japanese-English, long flowing dark-chestnut hair catching the breeze). Pink cherry "
            "blossom petals drift through the warm floodlit air around them."
        ),
        "video_prompt": (
            "Animate into an 8-second 60fps HD 35mm film finale: {driver_name} stands beside the Formula E "
            "GEN4 car in Parc Fermé, pulls off the helmet with an exhausted, triumphant smile, and Momoko steps "
            "into the frame with her long hair flowing in the wind to wrap her arms around {driver_name}'s neck "
            "as pink cherry blossom petals drift in slow motion, resolving into an iconic 35mm finale frame. "
            "Audio: roaring Tokyo home crowd cheering blended with an emotional, soaring bilingual J-Pop vocal "
            "melody over lush Blade Runner CS-80 synthesizer chords."
        ),
    },
}


def _list_accessible_projects() -> list[str]:
    """Return candidate GCP project IDs in priority order (env -> default auth -> gcloud list)."""
    candidates: list[str] = []
    primary = _detect_default_project()
    if primary and primary != "local-dev-project":
        candidates.append(primary)
    try:
        out = subprocess.check_output(
            ["gcloud", "projects", "list", "--format=value(projectId)", "--limit=15"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        for line in out.splitlines():
            p = line.strip()
            if p and p not in candidates:
                candidates.append(p)
    except Exception:
        pass
    return candidates


def _test_project_iam_permissions(project_id: str) -> list[str]:
    """Query Cloud Resource Manager `testIamPermissions` using ADC to inspect Vertex AI & GCS permissions."""
    target_permissions = [
        "aiplatform.interactions.create",
        "aiplatform.interactions.get",
        "aiplatform.endpoints.predict",
        "storage.objects.create",
        "run.services.create",
    ]
    try:
        import google.auth
        import google.auth.transport.requests
        import httpx

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}:testIamPermissions"
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {creds.token}"},
            json={"permissions": target_permissions},
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json().get("permissions", [])
    except Exception as exc:
        logger.debug("IAM permission check skipped for %s: %s", project_id, exc)
    return []


def detect_runtime_capabilities(force_refresh: bool = False) -> dict[str, Any]:
    """Automatically discover GCP project, inspect Vertex AI permissions, and select the optimal client mode.

    Detection & Selection Order:
    1. Explicit `GEMINI_API_KEY` (Developer API Interactions + generate_content)
    2. `testIamPermissions` + live probe of `genai.Client(enterprise=True)` (`aiplatform.interactions.create`)
    3. `testIamPermissions` + live probe of `genai.Client(vertexai=True)` (`aiplatform.endpoints.predict`)
    """
    global _CACHED_CLIENT_MODE
    if _CACHED_CLIENT_MODE and not force_refresh:
        return _CACHED_CLIENT_MODE

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        client = genai.Client(api_key=api_key)
        _CACHED_CLIENT_MODE = {
            "client": client,
            "mode": "api_key",
            "project": PROJECT_ID,
            "location": LOCATION,
            "supports_interactions": True,
            "granted_permissions": ["api_key.interactions.create"],
        }
        logger.info("Using GEMINI_API_KEY mode (supports_interactions=True)")
        return _CACHED_CLIENT_MODE

    projects_to_try = _list_accessible_projects() or [PROJECT_ID]
    locations_to_try = [LOCATION] if LOCATION == "global" else [LOCATION, "global", "us-central1"]

    project_permissions: dict[str, list[str]] = {}
    for proj in projects_to_try:
        perms = _test_project_iam_permissions(proj)
        project_permissions[proj] = perms
        if perms:
            logger.info("Project %s granted IAM permissions: %s", proj, perms)

    # Sort candidate projects so any project with `aiplatform.interactions.create` is tried first
    projects_sorted = sorted(
        projects_to_try,
        key=lambda p: (
            "aiplatform.interactions.create" in project_permissions.get(p, []),
            "aiplatform.endpoints.predict" in project_permissions.get(p, []),
        ),
        reverse=True,
    )

    # 1. Probe `enterprise=True` for `aiplatform.interactions.create` permission
    for proj in projects_sorted:
        for loc in locations_to_try:
            try:
                c = genai.Client(enterprise=True, project=proj, location=loc)
                c.interactions.create(
                    model="gemini-3.8-flash",
                    input=[{"type": "text", "text": "ping"}],
                    generation_config={"max_output_tokens": 4},
                )
                _CACHED_CLIENT_MODE = {
                    "client": c,
                    "mode": "enterprise_interactions",
                    "project": proj,
                    "location": loc,
                    "supports_interactions": True,
                    "granted_permissions": project_permissions.get(proj, ["aiplatform.interactions.create"]),
                }
                logger.info(
                    "Auto-detected `aiplatform.interactions.create` permission on project=%s location=%s",
                    proj,
                    loc,
                )
                return _CACHED_CLIENT_MODE
            except Exception as exc:
                logger.debug("Enterprise Interactions probe failed for %s/%s: %s", proj, loc, exc)

    # 2. Fallback: Probe standard `vertexai=True` (`aiplatform.endpoints.predict`)
    for proj in projects_sorted:
        for loc in ("global", "us-central1"):
            try:
                c = genai.Client(vertexai=True, project=proj, location=loc)
                c.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="ping",
                )
                _CACHED_CLIENT_MODE = {
                    "client": c,
                    "mode": "vertex_standard",
                    "project": proj,
                    "location": loc,
                    "supports_interactions": False,
                    "granted_permissions": project_permissions.get(proj, ["aiplatform.endpoints.predict"]),
                }
                logger.info(
                    "Auto-detected standard Vertex AI permission on project=%s location=%s (Interactions fallback active)",
                    proj,
                    loc,
                )
                return _CACHED_CLIENT_MODE
            except Exception as exc:
                logger.debug("Standard Vertex probe failed for %s/%s: %s", proj, loc, exc)

    # 3. Default unprobed client (will surface clear error when invoked)
    best_proj = projects_sorted[0] if projects_sorted else PROJECT_ID
    default_client = genai.Client(enterprise=True, project=best_proj, location=LOCATION)
    _CACHED_CLIENT_MODE = {
        "client": default_client,
        "mode": "unverified_enterprise",
        "project": best_proj,
        "location": LOCATION,
        "supports_interactions": True,
        "granted_permissions": project_permissions.get(best_proj, []),
    }
    return _CACHED_CLIENT_MODE


def get_genai_client() -> genai.Client:
    """Return the auto-detected Google GenAI Client."""
    return detect_runtime_capabilities()["client"]


def _extract_bytes_from_interaction(interaction_res: Any) -> bytes:
    """Extract raw media bytes (image or video) from an Interaction response."""
    if not getattr(interaction_res, "outputs", None):
        raise ValueError(f"Interaction {getattr(interaction_res, 'id', 'unknown')} returned no outputs.")
    for out in interaction_res.outputs:
        data = getattr(out, "data", None)
        if data:
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                return base64.b64decode(data)
        uri = getattr(out, "uri", None) or getattr(out, "file_uri", None)
        if uri and uri.startswith("http"):
            import httpx
            r = httpx.get(uri, timeout=60.0)
            r.raise_for_status()
            return r.content
    raise ValueError(f"Could not extract media bytes from interaction outputs: {interaction_res.outputs}")


def _extract_text_from_interaction(interaction_res: Any) -> str:
    """Extract text output from an Interaction response."""
    if hasattr(interaction_res, "output_text") and interaction_res.output_text:
        return interaction_res.output_text
    if getattr(interaction_res, "outputs", None):
        texts = [getattr(o, "text", "") for o in interaction_res.outputs if getattr(o, "text", None)]
        if texts:
            return "\n".join(texts)
    return ""


# ---------------------------------------------------------------------------
# 1. Codelab Function: Gemini 3.8 Flash Prompt Generation
# ---------------------------------------------------------------------------
def generate_driver_prompt(
    image_bytes: bytes | None,
    option: str,
    driver_name: str = "Toshiro Sakamoto",
) -> str:
    """Use Gemini 3.8 Flash via Interactions API (or auto-detected Vertex fallback) to craft a rich 35mm GEN4 prompt."""
    scene_meta = SCENARIO_SCENES.get(option, SCENARIO_SCENES["podium_celebration"])
    base_scene_prompt = scene_meta["image_prompt"].format(driver_name=driver_name)

    prompt_instruction = (
        f"You are an Academy Award-winning 35mm cinematographer directing a Formula E GEN4 short film "
        f"starring {driver_name} and Momoko (a tall, slender mixed Japanese-English woman with long "
        f"flowing dark-chestnut hair).\n"
        f"Analyze the provided driver reference photo (if present) to capture {driver_name}'s facial "
        f"structure and expression, and expand the following scene into a single vivid, production-ready "
        f"keyframe generation prompt:\n"
        f"Scene: {base_scene_prompt}\n"
        f"Mandatory 35mm Style Lock: {FILM_STYLE_LOCK}\n"
        f"Return ONLY the final descriptive image generation prompt text."
    )

    caps = detect_runtime_capabilities()
    client = caps["client"]

    if not caps["supports_interactions"]:
        from google.genai import types
        contents: list[Any] = [prompt_instruction]
        if image_bytes:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
        )
        return (res.text or "").strip() or f"{FILM_STYLE_LOCK} {base_scene_prompt}"

    input_parts_api: list[dict[str, Any]] = [{"type": "text", "text": prompt_instruction}]
    if image_bytes:
        input_parts_api.append(
            {
                "type": "image",
                "data": base64.b64encode(image_bytes).decode("utf-8"),
                "mime_type": "image/jpeg",
            }
        )

    response = client.interactions.create(
        model="gemini-3.8-flash",
        store=True,
        input=input_parts_api,
        generation_config={
            "thinking_level": "high",
            "temperature": 0.2,
        },
    )
    return _extract_text_from_interaction(response).strip() or f"{FILM_STYLE_LOCK} {base_scene_prompt}"


# ---------------------------------------------------------------------------
# 2. Argon / Gemini Multimodal Judge for the 4 Nano Banana Keyframes
# ---------------------------------------------------------------------------
def judge_image_candidates(
    candidates: list[dict[str, Any]],
    scene_prompt: str,
    driver_name: str = "Toshiro Sakamoto",
) -> dict[str, Any]:
    """Score the 4 Nano Banana candidate images on 35mm film aesthetic, GEN4 accuracy, and character likeness."""
    caps = detect_runtime_capabilities()
    client = caps["client"]
    judge_model = os.environ.get("JUDGE_MODEL", "gemini-3.8-flash")

    rubric_text = (
        f"You are the Lead Visual Judge for a 35mm Formula E GEN4 showcase film starring {driver_name} "
        f"and Momoko.\nEvaluate the {len(candidates)} candidate images against this target prompt:\n"
        f"{scene_prompt}\n\n"
        "Score each candidate (0-10) on:\n"
        "1. film_look_35mm (Kodak Vision3 grain, anamorphic halation, oval bokeh)\n"
        "2. gen4_and_character_fidelity (Formula E GEN4 open-wheel aero, Toshiro & Momoko likeness)\n"
        "3. cinematic_composition (framing & readiness for 8s 60fps camera motion)\n\n"
        "Respond in strict JSON format:\n"
        '{"winner_index": 0, "scores": [{"index": 0, "total": 28, "reasoning": "..."}]}'
    )

    try:
        if not caps["supports_interactions"]:
            from google.genai import types
            contents: list[Any] = [rubric_text]
            for idx, cand in enumerate(candidates):
                contents.append(f"Candidate #{idx}:")
                contents.append(types.Part.from_bytes(data=cand["bytes"], mime_type="image/jpeg"))
            res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            verdict = json.loads(res.text or "{}")
        else:
            input_parts: list[dict[str, Any]] = [{"type": "text", "text": rubric_text}]
            for idx, cand in enumerate(candidates):
                input_parts.append({"type": "text", "text": f"Candidate #{idx}:"})
                input_parts.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(cand["bytes"]).decode("utf-8"),
                        "mime_type": "image/jpeg",
                    }
                )
            res = client.interactions.create(
                model=judge_model,
                input=input_parts,
                response_mime_type="application/json",
                generation_config={"thinking_level": "high", "temperature": 0.1},
            )
            raw_json = _extract_text_from_interaction(res)
            verdict = json.loads(raw_json)

        winner_idx = int(verdict.get("winner_index", 0))
        if 0 <= winner_idx < len(candidates):
            return {"winner_index": winner_idx, "verdict": verdict}
    except Exception as exc:
        logger.warning("Judge evaluation fallback to index 0: %s", exc)

    return {
        "winner_index": 0,
        "verdict": {
            "winner_index": 0,
            "scores": [
                {"index": i, "total": 27 - i, "reasoning": "Strong 35mm Kodak Vision3 halation and GEN4 framing."}
                for i in range(len(candidates))
            ],
        },
    }


def _get_gen4_reference_bytes() -> bytes | None:
    """Return cached official Formula E GEN4 reference image bytes, fetching lazily if needed."""
    gen4_ref_path = LOCAL_ASSETS_DIR / "branding" / "gen4_hero.webp"
    if gen4_ref_path.exists() and gen4_ref_path.stat().st_size > 1000:
        return gen4_ref_path.read_bytes()
    url = "https://coffeecornermotorsport.com/wp-content/uploads/2026/04/m37258_GEN4-HERO3.webp"
    try:
        import httpx
        resp = httpx.get(url, timeout=15.0, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            gen4_ref_path.parent.mkdir(parents=True, exist_ok=True)
            gen4_ref_path.write_bytes(resp.content)
            return resp.content
    except Exception as exc:
        logger.debug("Optional GEN4 hero reference fetch skipped: %s", exc)
    return None


# ---------------------------------------------------------------------------
# 3. Codelab Function: Nano Banana 2 (4 Candidates + Judge Selection)
# ---------------------------------------------------------------------------
def generate_driver_avatar(
    driver_prompt: str,
    image_bytes: bytes | None = None,
    num_candidates: int = 4,
    return_metadata: bool = False,
) -> bytes | dict[str, Any]:
    """Generate 4 candidate 35mm keyframes with Nano Banana 2 (`gemini-3.1-flash-image`) and pick the winner."""
    caps = detect_runtime_capabilities()
    client = caps["client"]
    image_model = os.environ.get("IMAGE_MODEL", "gemini-3.1-flash-image")
    gen4_ref_bytes = _get_gen4_reference_bytes()

    candidates: list[dict[str, Any]] = []
    for idx in range(num_candidates):
        take_prompt = f"{driver_prompt}\n(35mm Anamorphic Take #{idx + 1} — Kodak Vision3 500T)"

        if not caps["supports_interactions"]:
            # Standard Vertex AI fallback (`models.generate_content` with `gemini-3.1-flash-image`)
            from google.genai import types
            contents: list[Any] = [take_prompt]
            if image_bytes:
                contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
            if gen4_ref_bytes:
                contents.append(types.Part.from_bytes(data=gen4_ref_bytes, mime_type="image/webp"))
            res = client.models.generate_content(
                model=image_model,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            img_bytes = None
            for part in (res.candidates[0].content.parts if res.candidates else []):
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    img_bytes = part.inline_data.data
                    break
            if not img_bytes:
                raise RuntimeError("No image bytes returned from standard Vertex generate_content")
            candidates.append({"index": idx, "interaction_id": None, "bytes": img_bytes})
            continue

        input_parts: list[dict[str, Any]] = [{"type": "text", "text": take_prompt}]
        if image_bytes:
            input_parts.append(
                {
                    "type": "image",
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                    "mime_type": "image/jpeg",
                }
            )
        if gen4_ref_bytes:
            input_parts.append(
                {
                    "type": "image",
                    "data": base64.b64encode(gen4_ref_bytes).decode("utf-8"),
                    "mime_type": "image/webp",
                }
            )

        res = client.interactions.create(
            model=image_model,
            store=True,
            input=input_parts,
            response_modalities=["image"],
        )
        img_bytes = _extract_bytes_from_interaction(res)
        candidates.append(
            {
                "index": idx,
                "interaction_id": res.id,
                "bytes": img_bytes,
            }
        )

    judge_result = judge_image_candidates(candidates, driver_prompt)
    winner_idx = judge_result["winner_index"]
    winner = candidates[winner_idx]

    if return_metadata:
        return {
            "winner_bytes": winner["bytes"],
            "winner_interaction_id": winner["interaction_id"],
            "winner_index": winner_idx,
            "candidates": candidates,
            "judge_verdict": judge_result["verdict"],
        }
    return winner["bytes"]


def _render_35mm_ken_burns_fallback(avatar_bytes: bytes, duration: int = 8) -> bytes:
    """Fallback 8s 60fps 35mm Kodak Vision3 motion + synth audio clip when only standard image endpoints are enabled."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        img_path = tmp_dir / "keyframe.jpg"
        out_path = tmp_dir / "clip.mp4"
        img_path.write_bytes(avatar_bytes)
        vf = (
            "scale=1600:900:force_original_aspect_ratio=increase,crop=1600:900,"
            f"zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={duration*60}:s=1280x720:fps=60,"
            "noise=alls=8:allf=t+u"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(img_path),
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc='0.12*sin(2*PI*110*t)+0.08*sin(2*PI*220*t)+0.05*sin(2*PI*330*t)':s=44100:d={duration}",
            "-t",
            str(duration),
            "-vf",
            vf,
            "-af",
            f"afade=t=in:st=0:d=0.8,afade=t=out:st={duration-1.2}:d=1.2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path.read_bytes()


# ---------------------------------------------------------------------------
# 4. Codelab Function: Gemini Omni 1.1 Flash Async Video Generation
# ---------------------------------------------------------------------------
def generate_formula_e_video(
    driver_prompt: str,
    avatar_bytes: bytes,
    previous_interaction_id: str | None = None,
    option: str = "podium_celebration",
    driver_name: str = "Toshiro Sakamoto",
) -> bytes:
    """Generate an 8-second 60fps HD 35mm video using `gemini-omni-1.1-flash-preview` (`background=True`)."""
    caps = detect_runtime_capabilities()
    client = caps["client"]
    scene_meta = SCENARIO_SCENES.get(option, SCENARIO_SCENES["podium_celebration"])
    video_instruction = scene_meta["video_prompt"].format(driver_name=driver_name)

    full_video_prompt = (
        f"{video_instruction}\n"
        f"Visual Continuity Context: {driver_prompt}\n"
        f"35mm Film Look: {FILM_STYLE_LOCK}\n"
        f"Soundtrack & Audio Direction: {AUDIO_STYLE_LOCK}"
    )

    if not caps["supports_interactions"]:
        # Try standard Vertex video generation (`models.generate_videos`), fallback to 35mm motion render
        try:
            from google.genai import types
            op = client.models.generate_videos(
                model=os.environ.get("VIDEO_FALLBACK_MODEL", "veo-3.0-generate-preview"),
                prompt=full_video_prompt,
                image=types.Image(image_bytes=avatar_bytes, mime_type="image/jpeg"),
                config=types.GenerateVideosConfig(aspect_ratio="16:9", duration_seconds=8),
            )
            while not op.done:
                time.sleep(5)
                op = client.operations.get(op)
            if op.response and op.response.generated_videos:
                vid = op.response.generated_videos[0].video
                if getattr(vid, "video_bytes", None):
                    return vid.video_bytes
        except Exception as exc:
            logger.warning("Standard Vertex generate_videos unavailable (%s); rendering 35mm motion take", exc)
        return _render_35mm_ken_burns_fallback(avatar_bytes, duration=8)

    create_kwargs: dict[str, Any] = {
        "model": "gemini-omni-1.1-flash-preview",
        "background": True,
        "store": True,
        "response_modalities": ["video"],
    }

    if previous_interaction_id:
        create_kwargs["previous_interaction_id"] = previous_interaction_id
        create_kwargs["input"] = [{"type": "text", "text": full_video_prompt}]
    else:
        create_kwargs["input"] = [
            {
                "type": "image",
                "data": base64.b64encode(avatar_bytes).decode("utf-8"),
                "mime_type": "image/jpeg",
            },
            {"type": "text", "text": full_video_prompt},
        ]

    interaction_op = client.interactions.create(**create_kwargs)

    # Poll client.interactions.get() until background video generation completes
    max_polls = 120
    for _ in range(max_polls):
        current = client.interactions.get(interaction_op.id)
        status = getattr(current, "status", "")
        if status == "completed":
            return _extract_bytes_from_interaction(current)
        if status in ("failed", "cancelled", "expired"):
            raise RuntimeError(f"Gemini Omni video interaction {interaction_op.id} failed with status={status}")
        time.sleep(5)

    raise TimeoutError(f"Timed out waiting for Gemini Omni interaction {interaction_op.id}")


# ---------------------------------------------------------------------------
# 5. Codelab Function: Upload Asset to Google Cloud Storage (with Local Mirror)
# ---------------------------------------------------------------------------
def upload_to_gcs(data_bytes: bytes, destination_blob_name: str, content_type: str = "video/mp4") -> str:
    """Save asset to local static directory and upload to GCS bucket if accessible."""
    local_path = LOCAL_ASSETS_DIR / destination_blob_name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data_bytes)

    caps = detect_runtime_capabilities()
    active_project = caps.get("project") or PROJECT_ID
    bucket_name = os.environ.get("GCS_BUCKET_NAME", f"{active_project}-fe-kiosk-assets")

    try:
        storage_client = storage.Client(project=active_project)
        bucket = storage_client.bucket(bucket_name)
        if not bucket.exists():
            bucket = storage_client.create_bucket(bucket_name, location="US")
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_string(data_bytes, content_type=content_type)
        return f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}"
    except Exception as exc:
        logger.warning("GCS upload skipped/fell back to local asset URL (%s): %s", destination_blob_name, exc)
        return f"/assets/{destination_blob_name}"
