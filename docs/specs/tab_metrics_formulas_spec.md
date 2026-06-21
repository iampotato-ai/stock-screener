# Spec: Screener Tab Formulas & Threshold Optimization

## Objective
Refine the color-coding logic, thresholds, and code redundancy for key metrics displayed under the Valuation, Quality, and Growth tabs in the main screener table (`renderTable()`). This improves visualization, aligns metrics with industry standards, incorporates sector-specific leverage and margin realities (e.g., banking leverage vs. normal company leverage, retail margins vs. high-margin sectors), and deduplicates simulated data indicator badges.

## Tech Stack
- Frontend: JavaScript (Vanilla)
- Component: main screener table renderer (`renderTable` in `app.js`)

## Success Criteria
- **Valuation Tab Refinements**:
  - **P/E Ratio**: Added color-coding: green (`val-up`) for PE < 15, red (`val-down`) for PE > 40.
  - **EV/EBITDA**: Added color-coding: green for EV/EBITDA < 10, red for EV/EBITDA > 20.
  - **P/B Ratio**: Added color-coding: green for PB < 1.5, red for PB > 5.
  - **FCF Yield**: Restrict green highlighting to meaningful yield values (FCF Yield >= 3%), instead of any positive yield.
- **Quality Tab Refinements**:
  - **CFO/PAT**: Relaxed red floor threshold from 50% to 40% to prevent misclassifying standard performance as poor.
  - **EBITDA Margin**: Incorporated sector awareness. For low-margin sectors ('Trading', 'Distribution', 'Retail', 'FMCG'), the green threshold is 8% (instead of 20%) and the red threshold is 3% (instead of 10%).
  - **D/E Ratio**: Incorporated sector awareness. For financial sectors ('Banking', 'Finance', 'NBFC', 'Insurance'), the green threshold is 5 (instead of 0.5) and the red threshold is 10 (instead of 1.5).
- **Growth Tab Refinements**:
  - **Revenue Growth QoQ**: Adjusted thresholds to prevent false positives: green >= 5% (instead of 4%), red < 0% (instead of 1.5%).
- **Code Deduplication**:
  - Extracted the repetitive simulated data badge logic into a helper function `simBadge(stock)` at the top of `renderTable()`.

## Proposed Changes

### [app.js](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/static/js/app.js)
- Define `simBadge(stock)` helper at the beginning of `renderTable()`.
- Update column rendering logic block for `pe_ratio`, `ev_ebitda`, `pb_ratio`, `fcf_yield`, `ebitda_margin`, `debt_to_equity`, `cfo_pat`, `wc_intensity`, `revenue_growth_qoq`, `revenue_growth_3y`, `ebitda_cagr`, and `eps_cagr`.

## Boundaries
- **Always:** Use standard styling classes (`val-up`, `val-down`, `val-na`) to preserve visual consistency.
- **Never:** Alter the database values or fields; changes must strictly reside in visual formatting logic.
- **Never:** Break the rendering of columns for active views or detail drawer sections.
