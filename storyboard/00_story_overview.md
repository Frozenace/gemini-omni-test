# Formula E Storyboard Overview: "Homecoming in Bloom"

## Logline
After losing his Formula 2 seat because his working-class family couldn't afford the millions required to stay on the grid, young Japanese driver **Toshiro Sakamoto** moves to the rainy UK alone to join a small British Formula E team (**Albion Electric Racing**). Supported by his mixed Japanese-English girlfriend **Momoko**, Toshiro fights his way from the simulator to the starting grid of his home race—the **Tokyo E-Prix at Tokyo Big Sight** during cherry blossom season.

## Global 35mm Film & Audio Look
- **Visual Style:** Shot on 35mm Kodak Vision3 film, Panavision anamorphic lenses, organic fine film grain, warm halation around highlights, shallow depth of field with oval bokeh, 180-degree shutter motion blur.
- **Audio & Soundtrack Style (Blade Runner x Futuristic J-Pop Mashup):** Lush Vangelis-style *Blade Runner* Yamaha CS-80 analog brass synthesizers and deep atmospheric rain/sub-bass drones in Act I, dropping into a high-energy, futuristic Cyberpunk J-Pop / Electro-Synthwave beat with ethereal bilingual Japanese/English vocals in Acts II & III, blended with the 600kW dual-motor scream of the Formula E GEN4 car.

## Codelab Pipeline Architecture (`genai.Client(enterprise=True)`)
1. **Prompt Director (`gemini-3.8-flash`):** Enhances scene & character inputs (`thinking_level="high"`, `temperature=0.2`) via `client.interactions.create()`.
2. **Nano Banana 2 (`gemini-3.1-flash-image`):** Generates **4 candidate 35mm reference keyframes** per scene (conditioned on the Character/Car sheets in [00_character_sheets.md](./00_character_sheets.md)) and stores them in Google Cloud Storage (GCS).
3. **Gemini 4 Argon Judge:** Evaluates the 4 candidate images for 35mm film look, character consistency (Toshiro Sakamoto & Momoko), and Formula E GEN4 car accuracy, selecting the winning keyframe.
4. **Gemini Omni Flash (`gemini-omni-1.1-flash-preview`):** Chains off the winning image via the **Interactions API** (`previous_interaction_id`, `background=True`, polling `client.interactions.get()`) to render an **8-second, 60fps HD** 35mm video clip with native Blade Runner x J-Pop audio.
5. **FastAPI Backend + Cloud Run Website:** Orchestrates the pipeline, serves assets from GCS, and stitches the 6 scenes into the master film.

---

## Scene Files (Edit Any File Directly)
- [00_character_sheets.md](./00_character_sheets.md) — **Character & Car Visual Locks** (Toshiro, Momoko, Albion GEN4 600kW AWD)
- [01_dawn_calm.md](./01_dawn_calm.md) — **Scene 01: Rainy UK Setback & Second Chance** (Silverstone/Oxfordshire damp track; Toshiro & Momoko in the British rain)
- [02_pit_awakening.md](./02_pit_awakening.md) — **Scene 02: Late Nights at the UK Factory** (Toshiro grinding in the simulator while Momoko watches from the glass booth)
- [03_grid_launch.md](./03_grid_launch.md) — **Scene 03: Arrival at Tokyo Big Sight** (Spring sakura in Ariake; a petal catches in Momoko's flowing hair as Toshiro steps into the pit garage)
- [04_sakura_vortex.md](./04_sakura_vortex.md) — **Scene 04: Grid Tension & Electric Launch** (Eye contact between Toshiro in the cockpit and Momoko in the pit lane before launching off the Tokyo line)
- [05_neon_apex.md](./05_neon_apex.md) — **Scene 05: The Ariake Sakura Vortex** (200 mph down the real Tokyo Bay waterfront straightaway, pulling pink cherry blossoms into a swirling slipstream tornado)
- [06_checkered_bloom.md](./06_checkered_bloom.md) — **Scene 06: Last-Corner Pass & Checkered Embrace** (Diving into the Tokyo Big Sight hairpin for the win and celebrating with Momoko under falling blossoms)
