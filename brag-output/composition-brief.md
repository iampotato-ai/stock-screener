# Hyperframes Composition Brief: MomentumScan

## Objective
Create a short launch-style brag video for MomentumScan - Indian Stock Screener & Quantitative Cockpit.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 18.0 seconds

## Source Material
- Project root: `c:\Users\91996\Documents\My Projects\stock-screener`
- Primary files read: `templates/index.html`, `static/css/fear_greed.css`, `README.md`, `AGENTS.md`
- Product name: MomentumScan
- Tagline / strongest claim: "Stop guessing NSE breakouts. Multi-model deep learning predictions, Episodic Pivot scoring, and institutional volume alerts."
- Key UI or visual elements to recreate:
  - Market Regime Speedometer Dial (0-100 gauge with EXTREME GREED badge)
  - Episodic Pivot (EP) Screener & Bull Snort Volume Alerts (Blue Accumulation & Orange Dry-up bars)
  - EnsembleCast Multi-Model Predictor Bar (Kronos Purple, Prophet Orange, ARIMA Cyan) & HIGH CONVICTION badge
  - MomentumScan dark glassmorphism aesthetic (`#0b0f19` bg, `#10b981` emerald glow)

## Creative Direction
- Tone preset: `polished`
- Creative direction: Institutional quantitative trading terminal product film.
- Interpretation: Sleek dark glass mode (`#0b0f19`), vibrant green accents (`#10b981`), high-contrast typography, precision motion, and confident holds.
- Angle: Trading NSE stocks without multi-model AI signals is like flying blind. MomentumScan aggregates Kronos, Prophet, and ARIMA forecasts alongside institutional accumulation alerts.
- Hook: "STOP GUESSING NSE BREAKOUTS" with animated Market Regime Speedometer dialing to 84 (EXTREME GREED).
- Outro / punchline: "MomentumScan: Your Institutional Cockpit for NSE."

## Visual Identity
- Background: `#0b0f19` (Dark Slate / Glass)
- Card / Panel Background: `rgba(15, 23, 42, 0.8)` with `1px solid rgba(255, 255, 255, 0.1)` border
- Text: `#f8fafc` (Slate 50)
- Primary Accent: `#10b981` (Emerald Green)
- Secondary Accents: `#7c3aed` (Kronos Purple), `#ea580c` (Prophet Orange), `#0891b2` (ARIMA Cyan), `#ef4444` (Red / Alert)
- Display font: Cabinet Grotesk / sans-serif fallback
- Body / Data font: Geist / IBM Plex Mono / monospace fallback

## Storyboard Summary
1. **Scene 1 — The Cockpit Hook** (0.0s - 4.0s): Dark glass cockpit bg. Headline "STOP GUESSING NSE BREAKOUTS". Dial sweeps 0->84 EXTREME GREED with green glow pulse.
2. **Scene 2 — Institutional Volume & EP Screener** (4.0s - 8.5s): EP Screener card (TATAMOTORS, RELIANCE) with green "EP TRIGGERED" badges + Bull Snort Volume Bars (Blue Accumulation & Orange Dry-Up).
3. **Scene 3 — EnsembleCast AI Deep Dive** (8.5s - 13.5s): EnsembleCast multi-model weights bar (Kronos 45% Purple, Prophet 35% Orange, ARIMA 20% Cyan) animating to full width + HIGH CONVICTION badge pop (+6.8% 5-day forecast).
4. **Scene 4 — Outro / MomentumScan Cockpit** (13.5s - 18.0s): MomentumScan title, emerald aura glow, "Launch Cockpit" CTA button.

## Audio
- Audio role: Warm energetic bed with crisp motion-matched click and reveal accents.
- Music: `assets/music/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3`
- Music treatment: Smooth 0.5s fade-in, steady posture, 1.5s fade-out at end.
- Music cue guidance: Preset available (`happy-beats-business-moves-vol-1-by-ende-dot-app.music-cues.json`).
  - Major cue lock at 3.02s (Scene 1 EXTREME GREED reveal)
  - Beat-grid sequence at 7.52s, 8.02s, 8.52s (Scene 2 stock cards)
  - Major cue lock at 12.02s (Scene 3 HIGH CONVICTION badge)
  - Major cue lock at 16.02s (Scene 4 Logo reveal)
- Audio-reactive treatment: Subtle emerald/purple aura glow on the regime dial and AI conviction badges breathing with music RMS.
- SFX choice: Crisp UI card clicks and counter tick sounds.

## Hyperframes Instructions
Use native HTML/CSS/JS and Hyperframes animation/rendering framework to construct `brag-output/composition/index.html`.
- Single 18-second video, 1920x1080@30fps.
- Maintain high legibility (contrast, font size, holds).
- Run `npx hyperframes check` in `brag-output/composition` as the pre-render gate.
