# Premium Stock Screener UI Design Specification

**Date:** 2026-06-18  
**Feature:** Workspace UI Premium Enhancement  
**Related:** feature/workspace-ui branch

## Grounding the Design

**Subject:** NSE India Swing & Intraday Momentum Stock Screener  
**Audience:** Active traders seeking institutional-grade tools for Indian equity markets  
**Page's Single Job:** Enable traders to screen, analyze, and execute trades with speed, confidence, and precision

## Color Palette

- **Primary:** Deep Indigo `#1E293B` (trust, stability, sophistication)
- **Accent:** Saffron Gold `#F59E0B` (growth, prosperity - cultural resonance)
- **Secondary:** Slate Gray `#64748B` (subtle hierarchy)
- **Success:** Emerald Green `#10B981` (positive momentum)
- **Error:** Red `#EF4444` (risk alerts)
- **Background:** Near-Black `#0F172A` (premium dark foundation)

*Rationale:* Avoids generic trading app blues/greens. The saffron accent provides distinctive warmth while maintaining professional credibility. The near-black background makes data pop and reduces eye strain during long trading sessions.

## Typography

- **Display:** IBM Plex Sans SemiBold (modern, highly readable, professional)
- **Body:** IBM Plex Sans Regular (optimized for data density)
- **Utility:** IBM Plex Mono (for tickers, numbers, codes - monospace clarity)
- **Type Scale:** 12px → 14px → 16px → 20px → 24px → 32px (intentional ratios)

*Rationale:* IBM Plex family offers excellent screen readability with subtle technical character. The mono utility face ensures numerical alignment in tables - critical for trading data.

## Layout Approach

- **Information First:** Market regime score as immediate visual priority
- **Progressive Disclosure:** Secondary controls in collapsible sections (aligns with Tier 1 UX plan)
- **Glassmorphism:** Subtle transparency in panels for depth without distraction
- **Data Hierarchy:** Most actionable data (prices, signals) in highest visual weight
- **Responsive:** Optimized for 13"+ trading laptop screens

## Signature Element: Market Pulse Visualization

Replace the standard regime gauge with a **dynamic radial flow indicator**:
- Circular visualization showing market energy as flowing particles
- Particle density/speed corresponds to regime score (0-100)
- Color shifts from deep blue (bearish) → saffron (neutral) → gold (bullish)
- Subtle animation that feels alive but not distracting
- Embedded delta badge showing daily change
- *Signature Rationale:* Transforms an abstract metric into an intuitive, memorable visual that traders can assimilate at a glance - more engaging than a gauge while conveying the same information

## Design Rationale

This avoids AI-generated defaults by:
1. **Cultural specificity:** Saffron accent ties to Indian financial prosperity symbolism
2. **Functional premium:** Every choice serves trading utility (monospace for numbers, clear hierarchy)
3. **Distinctive moment:** The Market Pulse creates brandable visual IP
4. **Professional restraint:** No unnecessary ornamentation - sophistication comes from execution quality

## Alignment with Existing Plans

This design complements and enhances the Tier 1 UX improvements documented in `docs/features/workspace-ui-tier1-ux.md` by:
- Providing the visual language for implementing those structural changes
- Elevating the Market Breadth & Sentiment Panel (Section 1 of Tier 1) with the Market Pulse
- Supporting the premium feel sought in all Tier 1 improvements