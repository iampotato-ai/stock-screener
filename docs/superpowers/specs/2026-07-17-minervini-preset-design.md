# Minervini Base / Target Preset Filter Design

**Date:** 2026‑07‑17

## Overview

Add a dedicated button inside the **Range & Advanced Filters** panel that, when toggled, automatically filters the screener to display only stocks whose Minervini stage is **Base** or **Target**. This provides swing‑traders a quick way to focus on the strongest setups without manually selecting stage chips.

## UI Changes

1. **Button markup** – placed after the “Stage” chip bar in `templates/index.html` (within `#range-filters-panel`).
   ```html
   <button id="btn-minervini-preset" class="btn btn-primary" onclick="window.toggleMinerviniPreset()">
       <i data-lucide="filter"></i> Minervini Base / Target
   </button>
   <input type="hidden" id="minervini-preset-flag" value="off">
   ```
   *The button receives an `active` class when the preset is on.*

2. **Styling** – reuse existing `.btn-primary` styles; add a small CSS rule for the active state if not already present:
   ```css
   #btn-minervini-preset.active { background: var(--accent-blue); color: #fff; }
   ```

## JavaScript Helper

Add to `static/js/app.js`:
```js
window.toggleMinerviniPreset = function() {
  const flag = document.getElementById('minervini-preset-flag');
  const isOn = flag.value === 'on';
  flag.value = isOn ? 'off' : 'on';
  const btn = document.getElementById('btn-minervini-preset');
  btn.classList.toggle('active', !isOn);
  filterAndRender();
};
```

## Filter Logic Adjustments

Update `filterAndRender()` (around line 3030) to read the hidden flag and adjust the stage filter:
```js
const minerviniPreset = document.getElementById('minervini-preset-flag').value === 'on';
let stageFilter = document.querySelector('#stage-filter-chips .filter-chip.active')?.dataset.value || 'all';
if (minerviniPreset) {
  // Force Base / Target regardless of chip selection
  stageFilter = ['Base', 'Target'];
} else if (stageFilter !== 'all') {
  stageFilter = [stageFilter]; // unify to array for later check
}
```

Later, when evaluating each stock:
```js
let matchesStage = true;
if (stageFilter.length && stageFilter[0] !== 'all') {
  matchesStage = stageFilter.includes(stock.stage_label);
}
```

## Backend (optional API shortcut)

Add an optional query parameter `stage_preset=base_target` to `GET /api/v1/screener/scan`.
In `app/services/screener_service.py` (inside `get_scan_results`), after the results list is built, apply:
```python
if request.args.get('stage_preset') == 'base_target':
    results = [s for s in results if s.get('stage_label') in ('Base', 'Target')]
```
*No DB changes needed; filtering happens in‑memory.*

## Testing Plan

| Test | Steps | Expectation |
|------|-------|-------------|
| **JS Unit** | Call `window.toggleMinerviniPreset()`; verify hidden flag toggles, button gets `active`, `filterAndRender` filters to Base/Target only. | Flag true, button styled, filtered array contains only allowed stages. |
| **E2E (Playwright)** | 1. Load screener page. 2. Click the preset button. 3. Wait for table render. 4. Assert every visible row’s *Stage* column is **Base** or **Target**. 5. Click the button again and verify mixed stages appear. | UI respects preset and clears correctly. |
| **API** (optional) | `GET /api/v1/screener/scan?stage_preset=base_target` → parse JSON. | All `stage_label` values are Base or Target. |

## Documentation Updates

- Add a subsection to `docs/specs/screener_header_layout_spec.md` describing the new button and hidden flag.
- Update `README.md` with a quick‑filter shortcut note.
- Document the `stage_preset` query param in the API reference.

---

*Implementation can now proceed via an implementation plan.*