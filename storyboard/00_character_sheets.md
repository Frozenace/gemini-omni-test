# Character & Asset Reference Sheets (For Nano Banana 4-Image Generation)

Use these prompts first to generate 4 candidate reference portraits per character/car with **Nano Banana** (`gemini-3.1-flash-image-preview`), judge the best one with **Gemini 4 Argon**, and pass the winning reference image into every scene's **Interactions API** chain.

---

## 1. Global 35mm Film Look (Apply to All Prompts)
> Shot on 35mm Kodak Vision3 500T film stock with Panavision C-Series anamorphic lenses. Authentic fine organic film grain, warm tungsten/amber halation around bright highlights, oval anamorphic bokeh, natural skin textures, cinematic color grade with deep rich shadows.

---

## 2. Toshiro Sakamoto (Protagonist Driver)
- **Backstory:** 22-year-old Japanese driver from a working-class background. Let go from Formula 2 right before his dream shot when family/sponsor money ran out. Moved to the UK alone to take a reserve-turned-race seat with a fictional British Formula E team (**Albion Electric Racing**).
- **Visual Anchor Prompt (Nano Banana — Generate 4 Candidates):**
  > Shot on 35mm Kodak Vision3 film, 50mm anamorphic portrait. Toshiro, a 22-year-old Japanese racing driver with sharp, determined eyes, wind-tousled short black hair, and a rugged, focused expression. He wears a matte slate-grey and electric-cyan Formula E racing suit ("Albion Racing") unzipped at the collar over a white fireproof nomex undershirt, holding a matte carbon helmet with a subtle hand-painted pink sakura branch motif along the jawline. Natural film grain, shallow depth of field, oval bokeh.

---

## 3. Momoko (Toshiro's Girlfriend & Emotional Anchor)
- **Backstory:** 21-year-old mixed Japanese-English woman who met Toshiro in the UK when he had nothing left after his F2 setback. She bridges his lonely life in rainy Britain and his homecoming race in Tokyo.
- **Visual Anchor Prompt (Nano Banana — Generate 4 Candidates):**
  > Shot on 35mm Kodak Vision3 film, 85mm anamorphic close-up portrait. Momoko, a tall, slender 22-year-old woman of mixed Japanese and English heritage, striking delicate features, warm expressive hazel-brown eyes, and long flowing dark-chestnut hair gently moving in the breeze. She wears a classic beige British trench coat with a Formula E VIP pit lane lanyard and oversized team radio headphones around her neck. Soft golden backlight with 35mm halation on her hair, fine film grain, oval bokeh.

---

## 4. The Car: Albion Electric Racing GEN4 (600kW Active AWD)
- **Official Gen4 Reference Image URL:** `https://coffeecornermotorsport.com/wp-content/uploads/2026/04/m37258_GEN4-HERO3.webp`
- **Specs:** Formula E GEN4 — 600 kW (815 bhp) Attack Mode power, permanent active All-Wheel Drive (AWD), 700 kW regenerative braking, wider Bridgestone sustainable tires, longer/wider sculpted high-downforce aero body (5,540mm length, 1,790mm width), 335+ km/h (208+ mph) top speed.
- **Visual Anchor Prompt (Nano Banana 2 / 2.1 — `gemini-3.1-flash-image` or `gemini-nano-banana-2.1` — Generate 4 Candidates conditioned on Official Gen4 Reference Image):**
  > Shot on 35mm Kodak Vision3 film, 35mm anamorphic three-quarter view. Transform the reference Formula E GEN4 open-wheel electric race car into a bespoke "Albion Electric Racing" livery: matte British racing slate-grey recycled carbon fiber, glowing electric cyan aero accents, and a subtle pink cherry blossom tribute stripe along the cockpit halo. Preserve the exact GEN4 sculpted front and rear wings, wider Bridgestone racing tires, and low-slung wide stance. Authentic 35mm film grain and halation.

---

## 5. Official Codelab Branding & Typography Assets
| Asset | Description | Source URL |
| :--- | :--- | :--- |
| **Gen4 Formula E Car** | Official Gen4 All-Electric Race Car Reference | `https://coffeecornermotorsport.com/wp-content/uploads/2026/04/m37258_GEN4-HERO3.webp` |
| **Formula E x Google Cloud Logo** | Co-branded Transparent Logo | `https://storage.googleapis.com/fe-demo-branding/formula_e_gc_logo_transparent.webp` |
| **Google Sans Regular Font** | Official Brand Typography | `https://storage.googleapis.com/fe-demo-branding/GoogleSans-Regular.ttf` |
| **Google Sans Medium Font** | Official Brand Typography | `https://storage.googleapis.com/fe-demo-branding/GoogleSans-Medium.ttf` |
