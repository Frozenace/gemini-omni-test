# Sakura in the Slipstream — Formula E GEN4 35mm Cinema & AI Kiosk

An end-to-end **35mm Kodak Vision3 Anamorphic Short Film Pipeline & Liquid Glass Interactive AI Kiosk** built on the **Gemini Platform Interactions API** (`genai.Client(enterprise=True)`), **Nano Banana 2** (`gemini-3.1-flash-image`), and **Gemini Omni 1.1 Flash** (`gemini-omni-1.1-flash-preview`), with **automatic GCP Project & Vertex AI IAM permission discovery**.

---

## 🎬 Story Overview: *"Sakura in the Slipstream"*

- **Protagonist:** **Toshiro Sakamoto** (22), a working-class Japanese racing prodigy dropped from Formula 2 when family sponsorship dried up. He relocates alone to the rainy UK to join fictional British Formula E squad **Albion Electric Racing**.
- **Co-Star:** **Momoko** (22), tall, slender, mixed Japanese-English with long flowing dark-chestnut hair—his anchor through rainy Silverstone/Oxfordshire nights and his homecoming at the **Tokyo E-Prix (Tokyo Big Sight, Ariake Waterfront)**.
- **The Machine:** **Formula E GEN4** (600kW Attack Mode, permanent active All-Wheel Drive, 700kW regenerative braking, 335 km/h / 208 mph top speed).
- **Visual & Audio Lock:** Shot on **35mm Kodak Vision3 500T** film stock with Panavision C-Series anamorphic lenses (organic grain, warm tungsten/cyan halation, oval bokeh), paired with a **Blade Runner (Vangelis CS-80 analog brass) × Futuristic Cyberpunk J-Pop** soundtrack.

### Storyboard Index ([`storyboard/`](./storyboard))
1. [`00_character_sheets.md`](./storyboard/00_character_sheets.md) — Character locks (Toshiro Sakamoto, Momoko) & GEN4 600kW AWD specs
2. [`00_story_overview.md`](./storyboard/00_story_overview.md) — 3-Act arc, 35mm aesthetic lock, and Interactions API chaining diagram
3. [`01_dawn_calm.md`](./storyboard/01_dawn_calm.md) — **Scene 01:** Rainy UK Setback & Second Chance (Oxfordshire Factory)
4. [`02_pit_awakening.md`](./storyboard/02_pit_awakening.md) — **Scene 02:** Late Nights at the UK Simulator Bay
5. [`03_grid_launch.md`](./storyboard/03_grid_launch.md) — **Scene 03:** Arrival at Tokyo Big Sight Waterfront Paddock
6. [`04_sakura_vortex.md`](./storyboard/04_sakura_vortex.md) — **Scene 04:** Grid Tension & 600kW Active-AWD Launch
7. [`05_neon_apex.md`](./storyboard/05_neon_apex.md) — **Scene 05:** The 208 mph Ariake Sakura Vortex
8. [`06_checkered_bloom.md`](./storyboard/06_checkered_bloom.md) — **Scene 06:** Last-Corner Pass, Parc Fermé Embrace & 35mm Finale Slate

---

## 🔐 Automatic Vertex AI & Project Permission Discovery

Zero hardcoded project IDs or credentials are required. On startup, [`detect_runtime_capabilities()`](./backend/app/services/gemini_service.py) automatically:
1. Detects the active GCP Project via environment variables (`GOOGLE_CLOUD_PROJECT`), `google.auth.default()`, or `gcloud config`.
2. Queries Cloud Resource Manager `testIamPermissions` across accessible projects for:
   - `aiplatform.interactions.create` & `aiplatform.interactions.get`
   - `aiplatform.endpoints.predict`
   - `storage.objects.create`
3. Automatically selects the optimal execution tier:
   - **`enterprise_interactions`** (`genai.Client(enterprise=True)`): Uses full stateful `client.interactions.create()` + `previous_interaction_id` chaining across **Gemini 3.8 Flash**, **Nano Banana 2** (`gemini-3.1-flash-image`), and **Gemini Omni 1.1 Flash** (`gemini-omni-1.1-flash-preview`).
   - **`vertex_standard`** (`genai.Client(vertexai=True)`): Automatically falls back to standard Vertex AI `models.generate_content` / `models.generate_videos` if `aiplatform.interactions.create` is not yet granted on the project.
   - **`api_key`**: Uses `GEMINI_API_KEY` if explicitly set.
4. Exposes live diagnostic output at `GET /api/health`.

---

## 🚀 Quickstart

### 1. Run the One-Step 6-Scene Fan-Out Pipeline (CLI)
Generates all 6 scenes (Gemini 3.8 Flash prompt $\rightarrow$ 4 Nano Banana keyframes $\rightarrow$ Judge selection $\rightarrow$ Gemini Omni 1.1 Flash 8s 60fps video chaining), appends the 4-second 35mm Finale Title Card via FFmpeg, runs the Final Cut Verification Judge, and writes `assets/showcase_manifest.json`:

```bash
cd backend && pip install -e . && cd ..
python3 run_pipeline.py
```

### 2. Run Locally (Backend + Liquid Glass Frontend)

**Terminal 1 — FastAPI Backend:**
```bash
cd backend
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — React + Vite Liquid Glass UI:**
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:8080` to switch between:
- **35mm Cinema Showcase:** Watch the stitched master film + inspect all 6 storyboard scenes, 4-candidate grids, and Judge scores.
- **Driver AI Kiosk (Step Into the Film):** Upload or snap your photo on webcam, enter your name (replacing *Toshiro Sakamoto*), pick any of the 6 scenes, and render a custom 35mm Formula E GEN4 clip.

### 3. One-Command Cloud Run Deployment
Automatically detects your GCP project, enables APIs, configures IAM bindings, creates the GCS bucket, and deploys both containers:

```bash
chmod +x deploy.sh
./deploy.sh
```
