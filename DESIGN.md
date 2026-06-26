---
name: MomentumScan
description: Institutional-grade NSE India stock screener with AI-powered forecasting
colors:
  primary: "#1E293B"
  accent: "#F59E0B"
  secondary: "#64748B"
  success: "#10B981"
  error: "#EF4444"
  background: "#0F172A"
  surface: "rgba(15, 23, 42, 0.7)"
  text-primary: "#F8FAFC"
  text-secondary: "#94A3B8"
  text-muted: "#64748B"
  accent-blue: "hsl(217, 95%, 62%)"
  accent-green: "hsl(142, 76%, 45%)"
  accent-red: "hsl(350, 80%, 55%)"
  accent-purple: "hsl(263, 85%, 64%)"
  accent-orange: "hsl(28, 90%, 55%)"
  bg-main: "hsl(230, 24%, 6%)"
  bg-gradient: "radial-gradient(ellipse at top, hsl(230, 24%, 9%) 0%, hsl(230, 24%, 5%) 100%)"
  panel-bg: "rgba(13, 17, 30, 0.45)"
  panel-border: "rgba(255, 255, 255, 0.05)"
  panel-border-hover: "rgba(255, 255, 255, 0.12)"
  glow-primary: "rgba(59, 130, 246, 0.15)"
  glow-purple: "rgba(139, 92, 246, 0.18)"
typography:
  display:
    fontFamily: "'Cabinet Grotesk', 'Geist', sans-serif"
    fontSize: "clamp(2.5rem, 7vw, 4.5rem)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "'Cabinet Grotesk', 'Geist', sans-serif"
    fontSize: "clamp(1.8rem, 5vw, 3rem)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.04em"
  title:
    fontFamily: "'Inter', 'Geist', sans-serif"
    fontSize: "clamp(1.5rem, 4vw, 2.5rem)"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  body:
    fontFamily: "'Geist', sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0"
  label:
    fontFamily: "'Inter', 'Geist', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0"
  mono:
    fontFamily: "'IBM Plex Mono', monospace"
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0"
rounded:
  sm: "6px"
  md: "10px"
  lg: "16px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.5rem"
  xxl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg} {spacing.xl}"
  button-primary-hover:
    backgroundColor: "{colors.accent}"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.md} {spacing.lg}"
  button-secondary-hover:
    backgroundColor: "{colors.accent}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
    padding: "{spacing.md} {spacing.lg}"
  button-ghost-hover:
    backgroundColor: "rgba(255, 255, 255, 0.05)"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
    border: "1px solid {colors.panel-border}"
  input-field-focus:
    borderColor: "{colors.accent-blue}"
    boxShadow: "0 0 0 2px rgba(59, 130, 246, 0.2)"
  input-field-error:
    borderColor: "{colors.error}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
    border: "1px solid {colors.panel-border}"
  card-hover:
    borderColor: "{colors.panel-border-hover}"
    boxShadow: "var(--shadow-premium)"
  chip:
    backgroundColor: "rgba(255, 255, 255, 0.05)"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm} {spacing.md}"
  chip-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.text-primary}"
  chip-outline:
    backgroundColor: "transparent"
    border: "1px solid {colors.panel-border}"
  chip-outline-active:
    borderColor: "{colors.accent}"
    textColor: "{colors.text-primary}"
  nav-item:
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  nav-item-active:
    textColor: "{colors.text-primary}"
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.accent}"
  glass-panel:
    backgroundColor: "{colors.panel-bg}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    border: "1px solid {colors.panel-border}"
  glass-panel-dark:
    backgroundColor: "rgba(15, 23, 42, 0.9)"
    borderColor: "rgba(148, 163, 184, 0.35)"

## 1. Overview

**Creative North Star: "The Institutional Trading Terminal"**

MomentumScan's design system embodies the precision and reliability of institutional trading terminals while maintaining accessibility for active traders. The interface prioritizes data density and actionable insights through a dark, premium aesthetic that reduces visual fatigue during extended trading sessions. Every element serves a functional purpose - from the conviction badges that communicate prediction confidence to the glass panels that provide depth without distraction.

### Key Characteristics:
- **Dark premium foundation** with strategic accent highlights for visual hierarchy
- **Data-first approach** where information density serves decision-making speed
- **Institutional-grade precision** in typography, spacing, and interactive states
- **Progressive disclosure** patterns to manage complexity without sacrificing depth
- **Consistent interaction language** across all modules and workflows

## 2. Colors

MomentumScan employs a restrained color strategy with deep navy as the primary background, anchored by a warm amber accent and supported by semantic blues, greens, and reds for different states and data visualizations.

### Primary
- **Deep Navy (#1E293B / hsl(217, 95%, 22%))**: Main background and primary surfaces, providing a dark, premium foundation that reduces eye strain during extended market hours

### Accent
- **Amber Gold (#F59E0B / hsl(48, 91%, 53%))**: Used for key interactive elements, highlighting important data points, and drawing attention to actionable items like primary buttons and active filters

### Secondary
- **Slate Gray (#64748B / hsl(214, 22%, 48%))**: Supporting elements, secondary text, and de-emphasized information that maintains hierarchy without competing for attention

### Semantic Colors
- **Emerald Success (#10B981 / hsl(142, 76%, 45%))**: Positive indicators, profitable trades, bullish signals, and confirmation states
- **Red Error (#EF4444 / hsl(350, 80%, 55%))**: Error states, stop-loss levels, bearish signals, and validation errors
- **Blue Info (#3B82F6 / hsl(217, 95%, 62%))**: Informational elements, neutral data points, and interactive states
- **Purple Warning (#8B5CF6 / hsl(263, 85%, 64%))**: Warning states, volatile indicators, and elevated risk notifications
- **Orange Attention (#F97316 / hsl(28, 90%, 55%))**: High-priority alerts, breakout signals, and attention-grabbing notifications

### Neutrals
- **Almost White (#F8FAFC / hsl(210, 40%, 98%))**: Primary text on dark surfaces for maximum readability
- **Cool Gray (#94A3B8 / hsl(210, 22%, 72%))**: Secondary text, placeholder content, and disabled states
- **Muted Slate (#64748B / hsl(214, 22%, 48%))**: Tertiary text, borders, and subtle dividers
- **Dark Surface (rgba(15, 23, 42, 0.7))**: Glass panels and overlay elements providing depth while maintaining darkness

## 3. Typography

MomentumScan utilizes a geometric sans-serif system optimized for data readability and institutional clarity, with Geist as the body font and Cabinet Grotesk for display elements.

### Display Font
**Cabinet Grotesk** (with Geist fallback): Used for logos, section headers, and high-impact numerical displays where strong visual presence is needed

### Body Font
**Geist** (with system sans-serif fallback): Primary interface text, table data, labels, and body content where legibility at small sizes is critical

### Label/Monospace Font
**Inter** for labels and **IBM Plex Mono** for code/data displays: Label text for form fields and monospace for technical displays like price tickers and timestamps

### Typographic Hierarchy
- **Display** (800, clamp(2.5rem, 7vw, 4.5rem), 1, -0.04em): Main headers, logos, and prominent numerical displays like regime scores
- **Headline** (700, clamp(1.8rem, 5vw, 3rem), 1.2, -0.04em): Section titles, important labels, and card headers
- **Title** (600, clamp(1.5rem, 4vw, 2.5rem), 1.3, -0.02em): Subsection headers, button texts, and meaningful labels
- **Body** (400, 0.9rem, 1.5, 0): Table cell content, tooltip bodies, and explanatory text
- **Label** (500, 0.75rem, 1.4, 0): Form labels, table headers, and instructional text
- **Mono** (400, 0.8rem, 1.4, 0): Data displays requiring fixed-width formatting like timestamps and codes

## 4. Elevation

MomentumScan employs a hybrid elevation system combining subtle shadows for depth perception with glassmorphism effects for modern, premium surfaces that maintain the dark aesthetic.

Elevation serves three purposes: indicating interactive states, creating visual hierarchy between panels, and providing depth without breaking the dark background paradigm.

### Shadow Vocabulary
- **Subtle Overlay** (`0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)`): Default state for interactive elements like buttons and chips
- **Focus Ring** (`0 0 0 2px rgba(59, 130, 246, 0.2)`): Interactive element focus states for accessibility
- **Elevated Panel Shadow`: Elevated buttons and active states`)
- **Premium Shadow** (`0 16px 48px -12px rgba(0, 0, 0, 0.5), inset 0 0 0 1px rgba(255, 255, 255, 0.05)`): Glass panels and modals for pronounced depth
- **Hover Lift** (`0 20px 40px -12px rgba(0, 0, 0, 0.65)`): Interactive elements on hover to communicate lift and interactivity

## 5. Components

### Buttons
- **Shape**: Rounded with 10px radius ({rounded.md})
- **Primary**: Deep navy background ({colors.primary}) with white text ({colors.text-primary}), 12px vertical and 24px horizontal padding ({spacing.lg} {spacing.xl}), transitions to amber accent on hover
- **Secondary**: Slate gray background ({colors.secondary}) with white text, 8px vertical and 16px horizontal padding ({spacing.md} {spacing.lg}), transitions to amber accent on hover
- **Ghost**: Transparent background with slate gray text ({colors.text-secondary}), 8px vertical and 16px horizontal padding, transitions to 5% white background on hover
- **States**: All buttons include explicit default, hover, focus-visible, active, and disabled states with appropriate visual treatments

### Inputs / Fields
- **Style**: Dark surface background ({colors.surface}) with white text ({colors.text-primary}), 1px slate border ({colors.panel-border}), 10px radius ({rounded.md}), 12px padding ({spacing.md})
- **Focus**: White text maintained, border shifts to accent blue ({colors.accent-blue}) with 2px outer glow
- **Error**: Border shifts to error red ({colors.error}) with appropriate visual treatment
- **Disabled**: Background becomes more transparent, text shifts to muted slate ({colors.text-muted})

### Cards / Containers
- **Corner Style**: 16px radius ({rounded.lg}) for main containers, 10px radius ({rounded.md}) for secondary containers
- **Background**: Dark surface color ({colors.surface}) with 1px slate border ({colors.panel-border})
- **Shadow Strategy**: Combines glassmorphism (blur and backdrop-filter) with subtle shadows for depth
- **Border**: 1px solid slate ({colors.panel-border}), shifting to panel-border-hover on interaction
- **Internal Padding**: 24px ({spacing.xl}) for primary containers, 16px ({spacing.lg}) for secondary containers

### Navigation
- **Style**: Horizontal tab bar with active state indicator
- **Typography**: Label style for tab text (Inter, 500, 0.75rem)
- **Default State**: Text-secondary color ({colors.text-secondary}) on transparent background
- **Active State**: Text-primary color ({colors.text-primary}) with accent underline or background shift
- **Hover State**: Slight background elevation to surface color
- **Mobile Treatment**: Collapses to sidebar or bottom navigation on narrow screens

### Signature Component: Conviction Badge
Used throughout the interface to communicate prediction confidence levels in AI-driven forecasts and analytics.
- **Style**: Pill-shaped container with 6px radius ({rounded.sm}), 6px horizontal and 4px vertical padding ({spacing.sm} {spacing.xs})
- **Color Mapping**:
  - HIGH: Emerald background with 15% opacity ({colors.success} at 0.15), emerald text, 1px border at 30% opacity
  - MODERATE: Amber background with 15% opacity ({colors.accent} at 0.15), amber text, 1px border at 30% opacity  
  - LOW: Red background with 15% opacity ({colors.error} at 0.15), red text, 1px border at 30% opacity
  - LOADING: Transparent white background with 5% opacity, muted text, subtle border

### Signature Component: Glass Panel
Reused throughout the interface for cards, modals, and containers requiring premium depth.
- **Style**: 16px radius ({rounded.lg}), backdrop-filter blur, 1px slate border, subtle premium shadow
- **Dark Variant**: 90% opaque dark background for night mode
- **Hover State**: Border lifts slightly with enhanced shadow and purple glow accent
- **Content Padding**: 24px standard ({spacing.xl}) for consistent internal spacing

### Signature Component: Filter Chip
Used in filter bars and tag interfaces for categorical filtering.
- **Style**: 6px radius ({rounded.sm}), 4px horizontal and 8px vertical padding ({spacing.xs} {spacing.sm})
- **Default**: Transparent background with muted text ({colors.text-muted}) and subtle border
- **Active**: Accent background ({colors.accent}) with white text ({colors.text-primary})
- **Outline Variant**: Transparent background with 1px border, shifting to accent border when active
- **Interaction**: Includes hover states with 5% white background lift

## 6. Do's and Don'ts

### Do:
- **Do** use the dark navy primary background (#1E293B) for all main surfaces to maintain visual consistency and reduce eye strain
- **Do** apply the amber accent (#F59E0B) sparingly (≤15% of any screen) for key interactive elements and important data highlights
- **Do** maintain 4.5:1 contrast ratio for all text against backgrounds, using almost white (#F8FAFC) for primary text on dark surfaces
- **Do** implement glassmorphism with backdrop-filter and subtle shadows for premium container depth
- **Do** use conviction badges with explicit color mapping to communicate prediction confidence levels
- **Do** follow the 8px/16px/24px spacing scale ({spacing.sm}/{spacing.md}/{spacing.xl}) for consistent rhythm
- **Do** apply 6px/10px/16px radius scale ({rounded.sm}/{rounded.md}/{rounded.lg}) for consistent corner treatment
- **Do** use Geist for body/table data and Cabinet Grotesk for display elements to maintain typographic hierarchy
- **Do** implement explicit hover, focus, active, and disabled states for all interactive components
- **Do** use semantic colors consistently: success (#10B981), error (#EF4444), info (#3B82F6), warning (#8B5CF6), attention (#F97316)

### Don't:
- **Don't** use light or warm-toned backgrounds that increase eye strain during extended trading sessions
- **Don't** use amber accent (>15% of screen) as it diminishes its effectiveness as a highlighting tool
- **Don't** violate contrast ratios - never use muted text on dark backgrounds without ensuring 4.5:1 minimum contrast
- **Don't** use flat containers without depth indicators - always apply glassmorphism or shadow treatments
- **Don't** use ambiguous confidence indicators - always employ the conviction badge system with explicit  ```

 10.