# Sector Rotation Timeline — Feature Spec

> **Feature ID:** `FEAT-004`  
> **Branch:** `feature/workspace-ui`  
> **Status:** 📋 Planned  
> **Priority:** High  
> **Component:** RRG Workspace Tab + Backend Breadth History

---

## 1. Overview

The current RRG (Relative Rotation Graph) is a **static snapshot** — it renders sector positions for the current session only. This feature upgrades it into an **animated 12-week sector rotation timeline**, showing how each sector has moved across the four RRG quadrants (Leading → Weakening → Lagging → Improving) over rolling 12-week windows.

The result is an interactive, scrub-able animation that reveals:
- Which sectors are **accelerating** into the Leading quadrant
- Which have **topped out** and are rotating into Weakening
- Historical context for the current session’s static snapshot
- Sector momentum paths directly relevant to industrials, capital goods, and metals rotation cycles

This is comparable to TradingView’s animated RRG feature — built natively inside the screener.

---

## 2. Goals

- Render 12 weeks of weekly RRG data per sector as an **animated trail** on the scatter plot.
- Support **Play / Pause / Scrub** controls so the user can step through frames manually.
- Trails fade from ghost (oldest) to solid (current) to give the rotation arc at a glance.
- Each sector dot is **clickable** at any frame to filter the screener to that sector.
- Reuse existing `sectorScores` computation logic — only the historical data layer is new.
- Fully contained within the existing **RRG workspace tab** — no new workspace tab required.

---

## 3. Data Model

### 3.1 RRG Coordinates Per Sector Per Week

Each weekly RRG frame needs two values per sector:

| Field | Formula | Description |
|---|---|---|
| `jdk_rs` (X-axis) | `sector_perf_4w / universe_median_4w * 100` | Relative Strength vs universe |
| `jdk_rs_momentum` (Y-axis) | `jdk_rs(this_week) - jdk_rs(last_week)` | Rate of change of RS |
| `week` | ISO week string (`YYYY-Www`) | Frame label |
| `sector` | Sector name string | e.g. `Capital Goods` |
| `score` | `sectorScores[sector].score` | Sector strength score (0–100) |
| `quadrant` | Derived from X/Y | `Leading`, `Weakening`, `Lagging`, `Improving` |

**Quadrant mapping:**

```
X > 100 AND Y > 100  → Leading
X > 100 AND Y < 100  → Weakening
X < 100 AND Y < 100  → Lagging
X < 100 AND Y > 100  → Improving
```

Centre is `(100, 100)` — universe benchmark.

---

### 3.2 History Storage

Weekly RRG snapshots are stored in a new SQLite table:

```sql
CREATE TABLE IF NOT EXISTS rrg_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    week        TEXT NOT NULL,          -- ISO week, e.g. '2026-W21'
    sector      TEXT NOT NULL,
    jdk_rs      REAL NOT NULL,          -- X-axis
    jdk_rs_momentum REAL NOT NULL,      -- Y-axis
    score       INTEGER,                -- sector strength score
    quadrant    TEXT,
    snapped_at  TEXT NOT NULL,          -- ISO datetime of insertion
    UNIQUE(week, sector)                -- one row per sector per week
);
```

Snapshot insertion uses `INSERT OR REPLACE` so re-runs during the same week overwrite cleanly.

---

## 4. Backend Changes

### 4.1 Weekly Snapshot Writer

Add a helper `snapshot_rrg_week()` to `app.py`, called:
- Once per day on the **first scan after market open** (guarded by a `_rrg_snapped_today` flag).
- Optionally via a new `POST /api/rrg/snapshot` route for manual triggering in dev.

```python
import datetime

_rrg_snapped_today = None

def snapshot_rrg_week(sector_scores_dict, universe_stocks):
    """
    Computes JDK RS and RS-Momentum for each sector and upserts into rrg_history.
    sector_scores_dict: the `sectorScores` dict already computed by calculate_sector_scores().
    universe_stocks:    the full universe list (used for median benchmark).
    """
    global _rrg_snapped_today
    today = datetime.date.today().isoformat()
    if _rrg_snapped_today == today:
        return  # already snapped this session

    iso_week = datetime.date.today().strftime('%Y-W%W')

    # Universe 4-week median return (benchmark)
    universe_4w = [s.get('perf_m', 0) or 0 for s in universe_stocks]
    uni_median  = statistics.median(universe_4w) if universe_4w else 0

    conn = get_db()
    cursor = conn.cursor()

    for sector, data in sector_scores_dict.items():
        if data.get('count', 0) < 2:
            continue  # skip sectors with insufficient stocks

        sector_4w = data.get('avg1M', 0) or 0
        jdk_rs = (sector_4w / uni_median * 100) if uni_median != 0 else 100.0

        # Fetch last week's jdk_rs to compute momentum
        cursor.execute(
            'SELECT jdk_rs FROM rrg_history WHERE sector = ? ORDER BY snapped_at DESC LIMIT 1',
            (sector,)
        )
        row = cursor.fetchone()
        prev_rs = row['jdk_rs'] if row else jdk_rs
        rs_momentum = jdk_rs - prev_rs

        # Quadrant
        if   jdk_rs >= 100 and rs_momentum >= 0: quadrant = 'Leading'
        elif jdk_rs >= 100 and rs_momentum <  0: quadrant = 'Weakening'
        elif jdk_rs <  100 and rs_momentum <  0: quadrant = 'Lagging'
        else:                                     quadrant = 'Improving'

        cursor.execute('''
            INSERT INTO rrg_history (week, sector, jdk_rs, jdk_rs_momentum, score, quadrant, snapped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week, sector) DO UPDATE SET
                jdk_rs           = excluded.jdk_rs,
                jdk_rs_momentum  = excluded.jdk_rs_momentum,
                score            = excluded.score,
                quadrant         = excluded.quadrant,
                snapped_at       = excluded.snapped_at
        ''', (iso_week, sector, jdk_rs, rs_momentum, data.get('score', 0), quadrant,
              datetime.datetime.utcnow().isoformat()))

    conn.commit()
    _rrg_snapped_today = today
```

Call site in the `/api/scan` handler, after `calculate_sector_scores()` resolves:
```python
# In /api/scan, after sector scores are computed:
if universe_data:
    snapshot_rrg_week(sector_scores, universe_data)
```

---

### 4.2 New API Endpoint

```
GET /api/rrg/history?weeks=12
```

**Query Params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `weeks` | `int` | `12` | Number of historical weeks to return (max 52) |
| `sectors` | `string` | _(all)_ | Comma-separated sector names to filter. Omit for all. |

**Response Shape:**

```json
{
  "weeks": 12,
  "generated_at": "2026-05-30T18:00:00",
  "frames": [
    {
      "week": "2026-W09",
      "sectors": [
        {
          "sector": "Capital Goods",
          "jdk_rs": 104.2,
          "jdk_rs_momentum": 1.8,
          "score": 78,
          "quadrant": "Leading"
        },
        {
          "sector": "Metals",
          "jdk_rs": 97.1,
          "jdk_rs_momentum": 2.3,
          "score": 61,
          "quadrant": "Improving"
        }
      ]
    },
    ...
  ]
}
```

Frames are returned **oldest → newest** so the frontend can animate in order.

**Handler skeleton:**

```python
@app.route('/api/rrg/history')
def rrg_history():
    weeks   = min(int(request.args.get('weeks', 12)), 52)
    sectors = request.args.get('sectors', '').split(',') if request.args.get('sectors') else None

    conn   = get_db()
    cursor = conn.cursor()

    query = '''
        SELECT week, sector, jdk_rs, jdk_rs_momentum, score, quadrant
        FROM rrg_history
        WHERE snapped_at >= datetime('now', ? || ' days')
        ORDER BY week ASC, sector ASC
    '''
    cursor.execute(query, (str(-weeks * 7),))
    rows = cursor.fetchall()

    # Group by week
    from collections import defaultdict
    frame_map = defaultdict(list)
    for r in rows:
        if sectors and r['sector'] not in sectors:
            continue
        frame_map[r['week']].append({
            'sector': r['sector'], 'jdk_rs': r['jdk_rs'],
            'jdk_rs_momentum': r['jdk_rs_momentum'],
            'score': r['score'], 'quadrant': r['quadrant']
        })

    frames = [{'week': w, 'sectors': s} for w, s in sorted(frame_map.items())]
    return jsonify({'weeks': weeks, 'generated_at': datetime.datetime.utcnow().isoformat(), 'frames': frames})
```

---

## 5. Frontend Changes

### 5.1 RRG Tab Layout Extension

Extend the existing `#rrg-container` with a timeline animation toolbar above the scatter plot:

```html
<!-- Insert above #rrg-chart inside #rrg-container -->
<div id="rrg-timeline-bar" class="rrg-timeline-bar">
  <div class="rrg-timeline-controls">
    <button id="btn-rrg-play"  class="btn-icon" title="Play animation">
      <svg><!-- play icon --></svg>
    </button>
    <button id="btn-rrg-pause" class="btn-icon hidden" title="Pause">
      <svg><!-- pause icon --></svg>
    </button>
    <button id="btn-rrg-reset" class="btn-icon" title="Reset to start">
      <svg><!-- skip-back icon --></svg>
    </button>
  </div>

  <input type="range" id="rrg-timeline-scrubber"
    min="0" max="11" value="11" step="1"
    class="rrg-scrubber" />

  <span id="rrg-week-label" class="rrg-week-label">Week: 2026-W21</span>

  <div class="rrg-timeline-right">
    <select id="rrg-weeks-select" class="select-sm">
      <option value="4">4 weeks</option>
      <option value="8">8 weeks</option>
      <option value="12" selected>12 weeks</option>
      <option value="26">26 weeks</option>
    </select>
    <button id="btn-rrg-snapshot-now" class="btn-ghost btn-xs" title="Save this week's snapshot manually">
      📸 Snap
    </button>
  </div>
</div>
```

---

### 5.2 Canvas Rendering — `renderRRGTimeline(frames, frameIndex)`

The RRG scatter plot is rendered on a `<canvas>`. Extend `renderRRG()` to accept a `frameIndex` parameter. Add a separate `renderRRGTrails(allFrames, currentFrameIndex)` function that draws faded ghost dots and connecting lines for historical positions.

```js
const RRG_SECTOR_COLORS = {
  'Capital Goods':     '#6366f1',
  'Metals':            '#f59e0b',
  'Industrial':        '#10b981',
  'Financial Services':'#3b82f6',
  'IT':                '#8b5cf6',
  'Healthcare':        '#ec4899',
  'Consumer':          '#f97316',
  'Energy':            '#14b8a6',
  'Infrastructure':    '#84cc16',
  'Auto':              '#ef4444',
};
const RRG_DEFAULT_COLOR = '#94a3b8';

let rrgHistoryFrames = [];     // All frames from /api/rrg/history
let rrgCurrentFrame  = 0;      // Currently displayed frame index
let rrgAnimTimer     = null;   // setInterval handle
const RRG_ANIM_INTERVAL_MS = 600; // ms per frame during auto-play

/**
 * Draws the full animated RRG for a given frame index.
 * @param {Array}  frames      - All history frames (oldest to newest)
 * @param {number} frameIdx    - Which frame to render as "current"
 */
function renderRRGTimeline(frames, frameIdx) {
  const canvas = document.getElementById('rrg-canvas');
  if (!canvas || !frames.length) return;

  const ctx    = canvas.getContext('2d');
  const W      = canvas.width;
  const H      = canvas.height;
  const pad    = 48;
  const cx     = W / 2;
  const cy     = H / 2;

  // Coordinate mappers: jdk_rs range 90–110, momentum range -5 to +5
  const RS_MIN = 88, RS_MAX = 112;
  const MO_MIN = -6, MO_MAX =  6;
  const toX = rs  => pad + ((rs - RS_MIN)  / (RS_MAX - RS_MIN))  * (W - pad * 2);
  const toY = mom => (H - pad) - ((mom - MO_MIN) / (MO_MAX - MO_MIN)) * (H - pad * 2);

  ctx.clearRect(0, 0, W, H);

  // --- Background quadrant fills ---
  const quadrantFills = [
    { x: cx, y: pad,  w: W - pad - cx, h: cy - pad,      color: 'rgba(16,185,129,0.04)',  label: 'Leading',   pos: [W - pad - 8, pad + 16] },
    { x: cx, y: cy,   w: W - pad - cx, h: H - pad - cy,  color: 'rgba(239,68,68,0.04)',   label: 'Weakening', pos: [W - pad - 8, H - pad - 8] },
    { x: pad, y: cy,  w: cx - pad,     h: H - pad - cy,  color: 'rgba(99,102,241,0.04)',  label: 'Lagging',   pos: [pad + 4, H - pad - 8] },
    { x: pad, y: pad, w: cx - pad,     h: cy - pad,      color: 'rgba(245,158,11,0.04)',  label: 'Improving', pos: [pad + 4, pad + 16] },
  ];
  quadrantFills.forEach(q => {
    ctx.fillStyle = q.color;
    ctx.fillRect(q.x, q.y, q.w, q.h);
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = q.pos[0] > cx ? 'right' : 'left';
    ctx.fillText(q.label, q.pos[0], q.pos[1]);
  });

  // --- Axis lines ---
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pad, cy); ctx.lineTo(W - pad, cy); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(cx, pad); ctx.lineTo(cx, H - pad); ctx.stroke();

  // --- Collect all unique sector names across frames ---
  const allSectors = [...new Set(frames.flatMap(f => f.sectors.map(s => s.sector)))];

  allSectors.forEach(sectorName => {
    const color = RRG_SECTOR_COLORS[sectorName] || RRG_DEFAULT_COLOR;
    const trailLen = Math.min(frameIdx + 1, frames.length);

    // Build the position trail for this sector up to frameIdx
    const trail = [];
    for (let i = Math.max(0, frameIdx - 11); i <= frameIdx; i++) {
      const frame = frames[i];
      const entry = frame?.sectors.find(s => s.sector === sectorName);
      if (entry) {
        trail.push({ x: toX(entry.jdk_rs), y: toY(entry.jdk_rs_momentum), score: entry.score, week: frame.week });
      }
    }
    if (!trail.length) return;

    // Draw trail lines (fading opacity older → newer)
    for (let i = 1; i < trail.length; i++) {
      const alpha = 0.1 + (i / trail.length) * 0.5;
      ctx.beginPath();
      ctx.strokeStyle = color + Math.round(alpha * 255).toString(16).padStart(2, '0');
      ctx.lineWidth = 1.5;
      ctx.moveTo(trail[i - 1].x, trail[i - 1].y);
      ctx.lineTo(trail[i].x, trail[i].y);
      ctx.stroke();
    }

    // Draw ghost dots (historical)
    for (let i = 0; i < trail.length - 1; i++) {
      const alpha = 0.12 + (i / trail.length) * 0.3;
      const r = 4 + (trail[i].score / 100) * 3;
      ctx.beginPath();
      ctx.arc(trail[i].x, trail[i].y, r, 0, Math.PI * 2);
      ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2, '0');
      ctx.fill();
    }

    // Draw current dot (full opacity, larger)
    const cur = trail[trail.length - 1];
    const curR = 6 + (cur.score / 100) * 5;
    ctx.beginPath();
    ctx.arc(cur.x, cur.y, curR, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Label
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.font = 'bold 10px Inter, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(sectorName, cur.x + curR + 4, cur.y + 4);
  });

  // --- Week label update ---
  const weekLabel = document.getElementById('rrg-week-label');
  if (weekLabel && frames[frameIdx]) weekLabel.textContent = `Week: ${frames[frameIdx].week}`;

  // --- Scrubber sync ---
  const scrubber = document.getElementById('rrg-timeline-scrubber');
  if (scrubber) scrubber.value = frameIdx;
}
```

---

### 5.3 Playback Controls

```js
function startRRGAnimation() {
  if (rrgAnimTimer) return;
  document.getElementById('btn-rrg-play')?.classList.add('hidden');
  document.getElementById('btn-rrg-pause')?.classList.remove('hidden');

  rrgAnimTimer = setInterval(() => {
    rrgCurrentFrame++;
    if (rrgCurrentFrame >= rrgHistoryFrames.length) {
      stopRRGAnimation();
      rrgCurrentFrame = rrgHistoryFrames.length - 1;
    }
    renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
  }, RRG_ANIM_INTERVAL_MS);
}

function stopRRGAnimation() {
  clearInterval(rrgAnimTimer);
  rrgAnimTimer = null;
  document.getElementById('btn-rrg-play')?.classList.remove('hidden');
  document.getElementById('btn-rrg-pause')?.classList.add('hidden');
}

function resetRRGAnimation() {
  stopRRGAnimation();
  rrgCurrentFrame = 0;
  renderRRGTimeline(rrgHistoryFrames, 0);
}
```

**Event listener wiring:**

```js
document.getElementById('btn-rrg-play')?.addEventListener('click',  startRRGAnimation);
document.getElementById('btn-rrg-pause')?.addEventListener('click', stopRRGAnimation);
document.getElementById('btn-rrg-reset')?.addEventListener('click', resetRRGAnimation);

document.getElementById('rrg-timeline-scrubber')?.addEventListener('input', e => {
  stopRRGAnimation();
  rrgCurrentFrame = parseInt(e.target.value);
  renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
});

document.getElementById('rrg-weeks-select')?.addEventListener('change', e => {
  loadRRGHistory(parseInt(e.target.value));
});

document.getElementById('btn-rrg-snapshot-now')?.addEventListener('click', () => {
  fetch('/api/rrg/snapshot', { method: 'POST' })
    .then(() => loadRRGHistory())
    .catch(() => {});
});
```

---

### 5.4 Data Loader

```js
async function loadRRGHistory(weeks = 12) {
  try {
    const res = await fetch(`/api/rrg/history?weeks=${weeks}`);
    const data = await res.json();
    rrgHistoryFrames = data.frames || [];
    rrgCurrentFrame  = Math.max(0, rrgHistoryFrames.length - 1);

    const scrubber = document.getElementById('rrg-timeline-scrubber');
    if (scrubber) {
      scrubber.max   = Math.max(0, rrgHistoryFrames.length - 1);
      scrubber.value = rrgCurrentFrame;
    }

    renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
  } catch (err) {
    console.error('RRG history load failed:', err);
  }
}
```

Call `loadRRGHistory()` inside the existing `switchWorkspace('rrg')` or `renderRRG()` entry point.

---

### 5.5 Sector Dot Click — Filter to Sector

Add a `click` listener on the RRG canvas. On click, hit-test the current frame’s sector positions and call `selectSector()` if within `curR + 4` pixels of a dot:

```js
document.getElementById('rrg-canvas')?.addEventListener('click', e => {
  if (!rrgHistoryFrames.length) return;
  const canvas  = e.currentTarget;
  const rect    = canvas.getBoundingClientRect();
  const mouseX  = e.clientX - rect.left;
  const mouseY  = e.clientY - rect.top;
  const frame   = rrgHistoryFrames[rrgCurrentFrame];
  if (!frame) return;

  // Same coordinate mappers as renderRRGTimeline
  const pad = 48;
  const RS_MIN = 88, RS_MAX = 112, MO_MIN = -6, MO_MAX = 6;
  const toX = rs  => pad + ((rs - RS_MIN)  / (RS_MAX - RS_MIN))  * (canvas.width  - pad * 2);
  const toY = mom => (canvas.height - pad) - ((mom - MO_MIN) / (MO_MAX - MO_MIN)) * (canvas.height - pad * 2);

  frame.sectors.forEach(s => {
    const dx = mouseX - toX(s.jdk_rs);
    const dy = mouseY - toY(s.jdk_rs_momentum);
    const hitR = 6 + (s.score / 100) * 5 + 6; // generous hit area
    if (Math.sqrt(dx * dx + dy * dy) <= hitR) {
      selectSector(s.sector);
      switchWorkspace('screener');
    }
  });
});
```

---

## 6. CSS

```css
/* Timeline bar */
.rrg-timeline-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  background: rgba(255,255,255,0.03);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-wrap: wrap;
}

.rrg-timeline-controls {
  display: flex;
  gap: 0.4rem;
}

/* Scrubber */
.rrg-scrubber {
  flex: 1;
  min-width: 120px;
  max-width: 320px;
  accent-color: #6366f1;
  cursor: pointer;
}

.rrg-week-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  min-width: 100px;
}

.rrg-timeline-right {
  margin-left: auto;
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

/* Quadrant legend */
.rrg-quadrant-legend {
  display: flex;
  gap: 1rem;
  padding: 0.4rem 1rem;
  font-size: 0.75rem;
}
.rrg-legend-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}
```

---

## 7. Graceful Degradation

| Scenario | Behaviour |
|---|---|
| `rrg_history` table is empty (first run) | Render only current session’s snapshot as a single frame; show `"Building history — check back next week"` label |
| `< 3` frames available | Render as static RRG; hide Play button and scrubber |
| Sector missing from a historical frame | Trail simply has a gap for that week; no error |
| Canvas not supported | Fall back to the existing non-animated RRG table view |
| `/api/rrg/history` fetch fails | Show existing static RRG; log error silently |

---

## 8. Acceptance Criteria

- [ ] Weekly RRG snapshots are upserted into `rrg_history` on the first scan of each trading day.
- [ ] `GET /api/rrg/history?weeks=12` returns frames grouped by week, oldest to newest.
- [ ] Animation plays through 12 frames at ~600ms per frame with Play/Pause/Reset controls.
- [ ] Scrubber correctly seeks to any historical week and re-renders the canvas.
- [ ] Sector trails are rendered with fading opacity (older = more transparent).
- [ ] Current-frame sector dot size scales with `score` (higher score = larger dot).
- [ ] Clicking a sector dot on any frame filters the screener table to that sector.
- [ ] Week selector (4 / 8 / 12 / 26) reloads the correct number of history frames.
- [ ] Gracefully renders with 0–2 frames (static fallback, no JS errors).
- [ ] `📸 Snap` manual trigger correctly writes a new `rrg_history` row and refreshes the animation.

---

## 9. Implementation Order

1. **DB schema:** Add `rrg_history` table to `init_db()` in `app.py`.
2. **Backend writer:** Implement `snapshot_rrg_week()` and wire it into `/api/scan`.
3. **Backend endpoint:** Implement `GET /api/rrg/history` and `POST /api/rrg/snapshot`.
4. **Seed historical data:** Backfill by calling `snapshot_rrg_week()` with mock weekly offsets using `perf_m` / `perf_3m` proxies to generate ~12 weeks of bootstrap data.
5. **Frontend toolbar HTML:** Add `#rrg-timeline-bar` to `templates/index.html` inside `#rrg-container`.
6. **Canvas renderer:** Implement `renderRRGTimeline()` in `static/js/rrg.js` (or inline in `app.js`).
7. **Playback controls:** Wire Play / Pause / Reset / Scrubber / Week-select listeners.
8. **Click-to-filter:** Wire canvas click handler for sector dot hit testing.
9. **CSS:** Add `.rrg-timeline-bar`, `.rrg-scrubber`, trail + ghost dot styles.
10. **Polish:** Quadrant colour legend strip, dot size scaling, label collision avoidance.

---

## 10. Backfill Strategy (Bootstrap)

Since the DB starts empty, generate synthetic historical frames from existing `perf_w` / `perf_m` / `perf_3m` data already returned by the scan:

| Proxy | Maps to | Weekly frame |
|---|---|---|
| `perf_w` | Current week RS | Week 0 (today) |
| `perf_m` / 4 | Approx 1-week average RS for past month | Weeks -1 to -4 |
| `perf_3m` / 12 | Approx 1-week average RS for past quarter | Weeks -5 to -12 |

Backfill is triggered once via `POST /api/rrg/backfill` (dev-only route) and never needs to run again once real weekly snapshots accumulate.

---

## 11. Related Files

| File | Change |
|---|---|
| `app.py` | `snapshot_rrg_week()`, `GET /api/rrg/history`, `POST /api/rrg/snapshot`, `POST /api/rrg/backfill`, DB schema update |
| `templates/index.html` | `#rrg-timeline-bar` toolbar, scrubber, play/pause/reset buttons, week selector |
| `static/js/rrg.js` _(new or inline)_ | `renderRRGTimeline()`, `startRRGAnimation()`, `stopRRGAnimation()`, `loadRRGHistory()`, click handler |
| `static/css/style.css` | Timeline bar, scrubber, ghost dot, trail line styles |

---

_Last updated: 2026-05-30_
