#!/usr/bin/env python3
"""One-Step Fan-Out Pipeline for 'Sakura in the Slipstream' (Toshiro Sakamoto & Momoko).

Executes:
1. Parallel/Sequential Scene Generation across all 6 Storyboard Scenes:
   - Gemini 3.8 Flash (`generate_driver_prompt`)
   - Nano Banana 2 (`generate_driver_avatar` -> 4 candidates + Judge selection)
   - Gemini Omni 1.1 Flash (`generate_formula_e_video` -> Chained via `previous_interaction_id`, 8s 60fps HD)
2. FFmpeg Master Mashup + 4s 35mm Finale Ending Slate (`stitch_scenes_with_ending`)
3. Multimodal Verification Judge (`verify_final_cut`)
4. Updates `assets/showcase_manifest.json` and uploads to Cloud Storage
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.main import jobs_db, run_full_film_pipeline


async def main() -> None:
    job_id = "cli-master-build"
    jobs_db[job_id] = {
        "status": "processing",
        "stage": "Starting CLI fan-out...",
        "result_url": None,
        "verification": None,
    }
    print("🎬 Starting 6-Scene 35mm Multimodal Chaining Pipeline for Toshiro Sakamoto & Momoko...")
    await run_full_film_pipeline(job_id, driver_name="Toshiro Sakamoto")
    final_state = jobs_db[job_id]
    print(f"Status: {final_state['status']}")
    print(f"Stage:  {final_state['stage']}")
    print(f"Output: {final_state.get('result_url')}")
    if final_state.get("verification"):
        print(f"Judge Verdict: {final_state['verification']}")


if __name__ == "__main__":
    asyncio.run(main())
