# Fundamental Analysis Tabs Enhancement Design
**Date**: 2026-06-19
**Related Tasks**: Task 13 (Design), Task 14 (Spec Writing)

## Overview
This document details the design for enhancing the Valuation, Quality, and Growth tabs in the Momentum Scan stock screener to provide better fundamental analysis capabilities for swing traders using a hybrid approach.

## Problem Statement
The current Valuation, Quality, and Growth tabs show basic metrics but lack:
1. Key fundamental metrics that swing traders need for decision making
2. Clear explanations of what metrics mean and how to interpret them
3. Logical grouping of related metrics
4. Trend/momentum visualization of fundamental data
5. Premium feel appropriate for a professional trading tool

## Solution Approach
Implement expandable detail sections within the existing stock detail drawer that appear contextually based on which fundamental tab is active. This leverages the familiar UI pattern users already know from other drawer sections (AI Forecast, Pattern Intelligence, History & Notes).

## Detailed Design

### Architecture
- Three new collapsible sections in the stock detail drawer:
  1. **Valuation Deep Dive** (shown when Valuation tab is active)
  2. **Quality Trends Analysis** (shown when Quality tab is active)  
  3. **Growth Momentum Signals** (shown when Growth tab is active)
- Each section contains 4-6 key metrics with explanations and visual indicators
- Metrics selected to provide actionable signals for swing trading decisions
- Visual presentation optimized for quick scanning and detailed interpretation

### Section Specifications

#### Valuation Deep Dive
Metrics:
1. **PEG Ratio** - P/E divided by earnings growth rate. <1.0 suggests undervalued relative to growth
2. **EV/Revenue** - Enterprise Value to Sales. Useful for comparing companies with different margins
3. **Yield Spread vs Sector** - (Stock EV/EBITDA - Sector Median EV/EBITDA). Shows relative cheapness
4. **Buyback Yield %** - Shares repurchased / Market Cap. Indicates shareholder commitment
5. **Debt/EBITDA** - Leverage ratio. Lower = more financial flexibility for growth
6. **Forward P/E vs 5Y Avg P/E** - % difference shows if expectations are rising/falling

#### Quality Trends Analysis
Metrics:
1. **Consecutive EPS Growth Quarters** - Shows consistency of execution (0-4+ quarters)
2. **Gross Margin Trend** - Last 4 quarters: ↑↑↑↑ (improving) to ↓↓↓↓ (declining)
3. **ROIC Trend** - Return on Invested Capital trend over last 4 quarters
4. **FCF Conversion %** - Free Cash Flow / EBITDA. >80% indicates high earnings quality
5. **Working Capital Trend** - Days of working capital tied up (lower is better trend)
6. **Earnings Surprise History** - Last 4 quarters: Beat/Miss/Meet pattern

#### Growth Momentum Signals
Metrics:
1. **QoQ Growth Acceleration** - Current quarter growth minus previous quarter growth
2. **YoY Growth Consistency** - Stability of growth over last 4 quarters (coefficient of variation)
3. **Analyst Revision Trend** - Net up/down revisions over last 30 days (↑↑↑ to ↓↓↓)
4. **Inventory Turnover Trend** - For product companies: rising = better demand
5. **Order Book/Backlog Growth** - Forward revenue visibility vs current revenue
6. **Segment Growth Contribution** - % of total growth coming from fastest-growing segment

### Visual Presentation

#### Section Container Styling
- Background: `rgba(255, 255, 255, 0.02)` 
- Border: `1px solid rgba(255, 255, 255, 0.04)`
- Border Radius: `6px`
- Padding: `0.8rem`
- Margin: `0.5rem top and bottom`

#### Section Header
- Flex layout: Icon + Title on left
- Font: `0.75rem`, uppercase, letter-spacing `0.05em`, font-weight `700`
- Color: `var(--color-text-muted)`
- Margin bottom: `0.6rem`

#### Metric Display Format
Each metric displayed as:
```
<div class="metric-row" style="display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0; border-bottom: 1px solid rgba(255,255,255,0.01);">
  <div class="metric-label" style="font-size: 0.8rem; color: var(--color-text-secondary); width: 60%;">
    <span class="metric-name">[Metric Name]</span>
    <span class="metric-help" style="font-size: 0.7rem; margin-left: 0.4rem; opacity: 0.7;" title="[Explanation]">ⓘ</span>
  </div>
  <div class="metric-value" style="font-size: 0.9rem; font-weight: 600; text-align: right; width: 35%;">
    <span class="metric-value-number">[Value]</span>
    <span class="metric-value-trend" style="font-size: 0.75rem; margin-left: 0.4rem;">[Trend Arrow]</span>
  </div>
</div>
```

#### Visual Indicators
- **Positive values/trends**: Green text (`var(--color-success, #10B981)`) with ↑ arrow
- **Negative values/trends**: Red text (`var(--color-error, #EF4444)`) with ↓ arrow  
- **Neutral/mixed**: Secondary text (`var(--color-text-secondary)`) with → arrow or no arrow
- **Help tooltips**: Small ⓘ icon with hover tooltip explaining the metric

### Information Flow Within Sections
Metrics ordered by importance and logical flow:
1. Primary signal metric (most actionable)
2. Trend/consistency metrics (showing momentum)  
3. Supporting/context metrics (additional confirmation)
4. Quality/validation metrics (risk factors or validation)

## Implementation Notes
- Uses existing drawer infrastructure - no new UI patterns to learn
- Leverages current tab switching mechanism to show/hide sections
- Follows existing CSS variable conventions for colors, spacing, typography
- Maintains responsiveness and accessibility standards
- Can be implemented incrementally by tab if needed

## Success Criteria
1. Users can access enhanced fundamental analysis within 2 clicks (click stock → see relevant drawer section)
2. Each metric includes clear explanation via tooltip
3. Visual indicators help quickly assess metric favorability
4. Metrics are logically grouped and flow naturally
5. Implementation maintains or improves performance
6. Design matches existing premium aesthetic of the application

## Next Steps
Upon approval of this design, proceed to implementation planning using the writing-plans skill to create detailed implementation tasks.