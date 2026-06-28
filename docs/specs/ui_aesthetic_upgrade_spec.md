# Spec: UI Aesthetic and Layout Upgrade

## Objective
Implement high-end visual refinements to the MomentumScan web application to establish a premium, state-of-the-art visual hierarchy. This includes custom branding SVG graphics, animated indicators, color-coded stat card funneling, real-time data status counters, session context banners, and layout alignment.

## Tech Stack
- Frontend: Vanilla HTML, CSS, JavaScript (running in browser)
- styling: Vanilla CSS, layout spacing utilities, CSS keyframe animations

## Commands
- Dev Server: `py run.py` (Runs on `http://127.0.0.1:5000`)

## Proposed Layout Changes

### 1. Header & Branding Bar
- **Logo Icon**: Replace the plain chart SVG with a custom vector featuring a diagonal trendline, breakout arrow, and blue-to-cyan gradient fill.
- **Header Separator**: Add a 1px bottom border under `.main-header` (`rgba(255,255,255,0.07)`).
- **Subtitle**: Change `letter-spacing` of "NSE India Screener" to `0.12em` and set uppercase tracking.
- **LIVE Dot & Status**:
  - Add a pulsing glow shadow animation to `.status-indicator.online`.
  - Add a real-time relative counter (e.g. `(Updated: 02:03:34 PM · 12s ago)`) updating every second.
  - Add a "Market Session Badge" next to status displaying `OPEN`, `CLOSED`, or `PRE-OPEN` based on IST trading hours.

### 2. Navigation Bar
- **Shimmer Background**: Add vertical shimmer gradient to the tabs container.
- **Active Tab Glow**: Map `box-shadow` glow to the sliding capsule background.
- **Inactive Tab Hover**: Lift tab by `1px` and show a subtle border.
- **Tab Icons**: Set icon `stroke-width` to `2.5` to make it visually heavier.
- **Bull Snort Tab**: Accent with an amber/gold color scheme and custom star/trophy polygon icon.

### 3. Screener Stat Cards Funnel
- **Color Funneling**:
  - Total Stocks: neutral border.
  - Elite Swing: soft blue border.
  - Strong Swing: teal/cyan border.
  - Sector Leaders: amber/gold border.
  - Breakout Ready: hot green border + glowing pulse shadow.
- **Progress Bars**: Add a 4px height relative-percentage progress bar at the bottom of each non-total card.
- **Staggered Count-Up**: Delay the initial load animation of cards incrementally (80ms delay per card).
- **Crossover Flash**: Briefly flash cards green (up) or red (down) when their values update.
- **Tooltips**: Add descriptive hover states to cards.

### 4. Spacing & Alignment
- **Spacers**: Reduce margins between nav bar and stat cards from `1.5rem` to `1.0rem`.
- **Alignment**: Center stat cards row with `justify-content: center` to align with the nav bar.

## Boundaries
- **Always**: Maintain absolute compatibility with existing search/filter logic.
- **Always**: Clean up any interval clocks on page unload or state change.

## Success Criteria
1. The header logo matches the breakout-arrow concept and the live indicator displays a ping pulse.
2. Nav active tab background slides smoothly and glows, while inactive tabs lift on hover.
3. The stat cards row is centered, color-coded, counts up with stagger, flashes on refresh, and updates relative progress bars.
4. The market badge correctly reports `OPEN`, `CLOSED`, or `PRE-OPEN` relative to Indian Standard Time (IST).
