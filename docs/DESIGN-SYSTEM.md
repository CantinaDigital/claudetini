# Claudetini Design System

> Last updated: 2026-02-17

---

## Table of Contents

1. [Theme Overview](#1-theme-overview)
2. [Color Tokens](#2-color-tokens)
3. [Typography](#3-typography)
4. [Spacing and Layout](#4-spacing-and-layout)
5. [Border Radius Conventions](#5-border-radius-conventions)
6. [UI Primitives Catalog](#6-ui-primitives-catalog)
7. [Animation Patterns](#7-animation-patterns)
8. [Icon System](#8-icon-system)
9. [Styling Rules and Best Practices](#9-styling-rules-and-best-practices)

---

## 1. Theme Overview

Claudetini uses a custom dark theme called **"Mission Control"** -- inspired by Bloomberg terminals, Linear, and Raycast. The visual language is built for information-dense developer dashboards: high contrast text on deep-black surfaces, accent colors used sparingly for semantic meaning, and monospace typography for data-heavy contexts.

**Design pillars:**

- **Dark-first.** There is no light mode. The entire palette is designed around a near-black base (`#0c0c0f`) with layered surfaces that gain subtle brightness.
- **Information density.** Small type sizes (9.5px--13px), tight padding, and compact components allow large amounts of project data to fit on screen without scrolling.
- **Semantic color.** Green, red, amber, and cyan are reserved for status communication (pass/fail/warn/info). Purple accent is the brand/interactive color. Colors are never decorative.
- **Monospace data, sans-serif prose.** Code paths, labels, timestamps, and data values use monospace. Prose and UI copy use the sans-serif stack.
- **Layered surfaces.** Five surface levels (`bg` through `surface-3`) create depth without shadows. Borders use white at very low alpha rather than solid gray.

### Token Architecture

Design tokens are defined in two mirrored locations:

| File | Purpose |
|------|---------|
| `app/src/styles/tokens.ts` | TypeScript constants for inline styles and SVG `fill`/`stroke` attributes |
| `app/tailwind.config.js` | Tailwind CSS utilities under the `mc-*` namespace |

Both files must stay in sync. The Tailwind config is the canonical source for class-based styling; the TypeScript tokens are used only when Tailwind classes cannot be applied (e.g., SVG attributes, computed dynamic values).

### Global Stylesheet

`app/src/styles/global.css` provides:

- Font imports (IBM Plex Mono, DM Sans, Satoshi)
- Base resets (box-sizing, font smoothing, body defaults)
- Custom scrollbar styling (6px wide, `#262630` thumb)
- Component-layer utility classes (`.mc-label`, `.mc-tag`, `.mc-severity-tag`)
- Keyframe definitions for all animations

---

## 2. Color Tokens

All custom colors use the `mc-` prefix in Tailwind classes. The prefix stands for "Mission Control."

### 2.1 Surfaces

Surfaces are layered from darkest (background) to lightest (surface-3). Use higher surface numbers for elevated elements like cards, modals, and dropdowns.

| Token Name | Hex | Tailwind Class | Usage |
|------------|-----|----------------|-------|
| `bg` | `#0c0c0f` | `bg-mc-bg` | Page/app background |
| `surface0` | `#111116` | `bg-mc-surface-0` | Base card background, skeleton card |
| `surface1` | `#18181f` | `bg-mc-surface-1` | Section panels, modal body, dialog background |
| `surface2` | `#1f1f28` | `bg-mc-surface-2` | Input fields, tags, dropdown triggers, select menus |
| `surface3` | `#262630` | `bg-mc-surface-3` | Hover states, active toggles (off), inline code background |

### 2.2 Borders

Borders use white at very low alpha values to create subtle separation without hard lines.

| Token Name | Value | Tailwind Class | Usage |
|------------|-------|----------------|-------|
| `border0` | `rgba(255,255,255,0.04)` | `border-mc-border-0` | Section dividers, card borders, subtle separators |
| `border1` | `rgba(255,255,255,0.07)` | `border-mc-border-1` | Input borders, dropdown borders, toggle borders (off) |
| `border2` | `rgba(255,255,255,0.12)` | `border-mc-border-2` | Ghost button borders, stronger emphasis borders |

### 2.3 Text

Four text levels provide a clear hierarchy from brightest (headings, primary content) to dimmest (disabled, tertiary metadata).

| Token Name | Hex | Tailwind Class | Usage |
|------------|-----|----------------|-------|
| `text0` | `#f0f0f5` | `text-mc-text-0` | Headings, primary content, toast titles, dialog titles |
| `text1` | `#c8c8d4` | `text-mc-text-1` | Body text, selected option labels, inline code text |
| `text2` | `#8b8b9e` | `text-mc-text-2` | Secondary text, muted descriptions, toast messages, diff context lines |
| `text3` | `#5c5c6e` | `text-mc-text-3` | Tertiary text, labels, timestamps, disabled content, tag defaults |

### 2.4 Accent (Purple)

The primary brand and interactive color. Used for active states, primary buttons, selected items, and focus indicators.

| Token Name | Value | Tailwind Class | Usage |
|------------|-------|----------------|-------|
| `accent` | `#8b7cf6` | `text-mc-accent`, `bg-mc-accent` | Primary buttons, toggle (on), selected checkmarks, info toast icon |
| `accentDark` | `#6d5bd0` | `bg-mc-accent-dark` | Gradient endpoint for progress bars and badges |
| `accentMuted` | `rgba(139,124,246,0.12)` | `bg-mc-accent-muted` | Info toast background, accent badge background |
| `accentBorder` | `rgba(139,124,246,0.25)` | `border-mc-accent-border` | Info toast border, toggle border (on), accent highlights |

### 2.5 Green (Success)

Used exclusively for success states: passed gates, completed items, positive diffs.

| Token Name | Value | Tailwind Class | Usage |
|------------|-------|----------------|-------|
| `green` | `#34d399` | `text-mc-green`, `bg-mc-green` | Success toast icon, StatusDot (pass), diff additions, Sparkline (full) |
| `greenLight` | `#2dd4a0` | `bg-mc-green-light` | Gradient endpoint for progress bars |
| `greenMuted` | `rgba(52,211,153,0.1)` | `bg-mc-green-muted` | Success toast background, SeverityTag (pass) background |
| `greenBorder` | `rgba(52,211,153,0.2)` | `border-mc-green-border` | Success toast border, SeverityTag (pass) border |

### 2.6 Red (Error / Danger)

Used for error states, failures, destructive actions, and diff deletions.

| Token Name | Value | Tailwind Class | Usage |
|------------|-------|----------------|-------|
| `red` | `#f87171` | `text-mc-red`, `bg-mc-red` | Danger buttons, error toast icon, StatusDot (fail), diff deletions |
| `redMuted` | `rgba(248,113,113,0.08)` | `bg-mc-red-muted` | Error toast background, SeverityTag (fail/error) background |
| `redBorder` | `rgba(248,113,113,0.18)` | `border-mc-red-border` | Error toast border, SeverityTag (fail/error) border, danger dialog border |

### 2.7 Amber (Warning)

Used for warning states and medium-severity indicators.

| Token Name | Value | Tailwind Class | Usage |
|------------|-------|----------------|-------|
| `amber` | `#fbbf24` | `text-mc-amber`, `bg-mc-amber` | Warning toast icon, StatusDot (warn), Sparkline (mid-range) |
| `amberMuted` | `rgba(251,191,36,0.08)` | `bg-mc-amber-muted` | Warning toast background, SeverityTag (warn) background |
| `amberBorder` | `rgba(251,191,36,0.18)` | `border-mc-amber-border` | Warning toast border, SeverityTag (warn) border |

### 2.8 Cyan (Informational / Branch)

Used for branch-related indicators, diff hunk headers, and secondary informational highlights.

| Token Name | Value | Tailwind Class | Usage |
|------------|-------|----------------|-------|
| `cyan` | `#22d3ee` | `text-mc-cyan`, `bg-mc-cyan` | Diff hunk headers (`@@`), branch strategy indicators |
| `cyanMuted` | `rgba(34,211,238,0.12)` | `bg-mc-cyan-muted` | Cyan badge backgrounds |
| `cyanBorder` | `rgba(34,211,238,0.25)` | `border-mc-cyan-border` | Cyan badge borders |

### 2.9 StatusDot Glow Values

The `StatusDot` component applies a `box-shadow` glow using these RGBA values (not available as Tailwind classes -- used via inline styles only):

| Status | Glow Value |
|--------|------------|
| `pass` | `rgba(52,211,153,0.4)` |
| `warn` | `rgba(251,191,36,0.4)` |
| `fail` | `rgba(248,113,113,0.5)` |

---

## 3. Typography

### 3.1 Font Stacks

| Role | Fonts | Tailwind Class | Loaded From |
|------|-------|----------------|-------------|
| **Sans-serif** | Satoshi, DM Sans, -apple-system, sans-serif | `font-sans` | Fontshare (Satoshi), Google Fonts (DM Sans) |
| **Monospace** | IBM Plex Mono, JetBrains Mono, monospace | `font-mono` | Google Fonts (IBM Plex Mono) |

Both stacks include system fallbacks. Satoshi is loaded from Fontshare (`api.fontshare.com`); IBM Plex Mono and DM Sans from Google Fonts. Weights 400, 500, 600, and 700 are imported.

### 3.2 Font Sizes in Use

The design system uses a tight range of small sizes appropriate for data-dense dashboards. Sizes are specified in pixels via Tailwind arbitrary values.

| Size | Tailwind Class | Typical Usage |
|------|----------------|---------------|
| `9.5px` | `text-[9.5px]` | Severity tags (`.mc-severity-tag`) |
| `10px` | `text-[10px]` | Labels (`.mc-label`), tags (`.mc-tag`), section right-side metadata |
| `10.5px` | `text-[10.5px]` | Select trigger (small), diff block code |
| `11px` | `text-[11px]` | Small buttons, toast icon text |
| `12px` | `text-xs` (Tailwind) | Standard buttons, select options, toast messages |
| `12.5px` | `text-[12.5px]` | Dialog body text |
| `13px` | `text-[13px]` | Toast title |
| `14px` | `text-sm` (Tailwind) | Dialog header title |

### 3.3 Font Weights

| Weight | Tailwind Class | Usage |
|--------|----------------|-------|
| 400 (Regular) | `font-normal` | Body text, unselected options |
| 500 (Medium) | `font-medium` | Select trigger text |
| 600 (Semibold) | `font-semibold` | Buttons, tags, selected options, toast titles |
| 700 (Bold) | `font-bold` | Labels, severity tags, dialog titles, diff section headers |

### 3.4 Letter Spacing

| Value | Tailwind Class | Usage |
|-------|----------------|-------|
| `0.05em` | `tracking-[0.05em]` | Tags (`.mc-tag`) |
| `0.06em` | `tracking-[0.06em]` | Severity tags (`.mc-severity-tag`) |
| `0.08em` | `tracking-[0.08em]` | Labels (`.mc-label`) |

### 3.5 Line Heights

| Value | Tailwind Class | Usage |
|-------|----------------|-------|
| `1` | `leading-4` (16px) | Tags, severity tags |
| `1.55` | `leading-[1.55]` | Diff block lines |
| `1.625` | `leading-relaxed` | Dialog body text |

---

## 4. Spacing and Layout

### 4.1 Spacing Scale

The design system follows Tailwind's default spacing scale (4px base) with select arbitrary values for fine-tuning.

**Common spacing values used across components:**

| Spacing | Tailwind Class | Usage |
|---------|----------------|-------|
| `2px` | `py-[2px]`, `gap-0.5` | Tag vertical padding, tight gaps |
| `3px` | `left-[3px]` | Toggle knob offset (off) |
| `4px` | `p-1`, `gap-1` | Icon gaps, minimal padding |
| `5px` | `gap-[5px]`, `px-[5px]` | Button icon gap, inline code horizontal padding |
| `6px` | `gap-1.5` | Select icon-to-label gap |
| `7px` | `px-[7px]` | Tag and severity tag horizontal padding |
| `8px` | `p-2`, `gap-2` | Skeleton text line gaps, toast stack gap |
| `10px` | `gap-2.5`, `py-2.5`, `px-2.5` | Skeleton gaps, small button horizontal padding |
| `11px` | `py-[11px]` | Section header vertical padding |
| `12px` | `p-3`, `gap-3`, `px-3` | Toast content gap, diff block padding, button horizontal padding |
| `14px` | `px-3.5`, `py-3.5` | Standard button horizontal padding, skeleton card padding |
| `16px` | `p-4`, `px-4` | Section body padding, toast horizontal padding |
| `18px` | `px-[18px]` | Skeleton card inner padding |
| `20px` | `p-5`, `px-5` | Dialog section padding, toast container offset |

### 4.2 Layout Patterns

**Section layout:** Sections use a header/body split. The header contains a label on the left and optional metadata on the right, separated by `justify-between`. The body is unstyled to allow flexible content.

**Dialog layout:** Three vertical zones -- header (title), body (message), and actions (buttons) -- each separated by `border-mc-border-0` dividers. The actions row is right-aligned with a `gap-2`.

**Toast container:** Fixed position at `bottom-5 right-5`, stacked vertically with `gap-2`, at `z-[9999]`.

**Dropdown menus:** Positioned `top-[calc(100%+4px)]` below their trigger, with `z-[1000]` and heavy box shadow.

---

## 5. Border Radius Conventions

| Radius | Tailwind Class | Usage |
|--------|----------------|-------|
| `1px` | `rx={1}` (SVG) | Sparkline bar corners |
| `3px` | `rounded` | Scrollbar thumb |
| `4px` | `rounded` | Tags, severity tags, inline code |
| `6px` | `rounded-md` | Buttons, select triggers, default Skeleton |
| `8px` | `rounded-lg` | Toasts, dropdown menus, diff blocks, skeleton rows |
| `10px` | `rounded-[10px]` | Toggle track, skeleton cards |
| `12px` | `rounded-xl` | Sections, dialogs |
| `full` | `rounded-full` | StatusDot, toggle knob, toast icon circle |

**General rule:** Interactive elements (buttons, inputs) use `rounded-md`. Container elements (sections, dialogs) use `rounded-xl`. Pill-shaped elements (toggles, dots) use `rounded-full`.

---

## 6. UI Primitives Catalog

All primitives live in `app/src/components/ui/`.

---

### 6.1 Button

**File:** `app/src/components/ui/Button.tsx`

A flexible button component with three visual variants and two sizes.

#### Props Interface

```typescript
interface ButtonProps {
  children: ReactNode;
  primary?: boolean;    // Purple accent background
  danger?: boolean;     // Red background (takes precedence over primary)
  small?: boolean;      // Compact size variant
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
  className?: string;   // Additional Tailwind classes
  disabled?: boolean;   // Reduces opacity, disables interaction
  title?: string;       // Native tooltip
}
```

#### Variants

| Variant | Visual | Classes |
|---------|--------|---------|
| **Ghost** (default) | Transparent with border | `bg-transparent border border-mc-border-2 text-mc-text-2` |
| **Primary** | Solid purple | `bg-mc-accent text-white border-none` |
| **Danger** | Solid red | `bg-mc-red text-white border-none` |

#### Sizes

| Size | Padding | Font Size |
|------|---------|-----------|
| **Default** | `px-3.5 py-1.5` | `text-xs` (12px) |
| **Small** | `px-2.5 py-1` | `text-[11px]` |

#### Usage

```tsx
import { Button } from "../ui/Button";

// Ghost button
<Button onClick={handleClick}>Cancel</Button>

// Primary action
<Button primary onClick={handleSave}>Save Changes</Button>

// Destructive action
<Button danger onClick={handleDelete}>Delete Project</Button>

// Small variant
<Button small primary onClick={handleRun}>Run</Button>

// Disabled state
<Button primary disabled>Processing...</Button>
```

---

### 6.2 Tag

**File:** `app/src/components/ui/Tag.tsx`

An inline label for categorization and metadata display. Uses the `.mc-tag` utility class.

#### Props Interface

```typescript
interface TagProps {
  children: React.ReactNode;
  color?: string;  // Override text color (CSS value)
  bg?: string;     // Override background color (CSS value)
}
```

#### Default Styling

Applies `.mc-tag` which resolves to: `text-[10px] font-semibold font-mono tracking-[0.05em] py-[2px] px-[7px] rounded uppercase leading-4 inline-block`. Default colors: `bg-mc-surface-2 text-mc-text-3`.

#### Usage

```tsx
import { Tag } from "../ui/Tag";

// Default tag
<Tag>milestone</Tag>

// Custom colors
<Tag color="#34d399" bg="rgba(52,211,153,0.1)">COMPLETE</Tag>
```

---

### 6.3 SeverityTag

**File:** `app/src/components/ui/SeverityTag.tsx`

A status-aware tag that maps status values to predefined color schemes. Uses the `.mc-severity-tag` utility class.

#### Props Interface

```typescript
type TagStatus = "pass" | "warn" | "fail" | "skipped" | "error";

interface SeverityTagProps {
  status: TagStatus;
}
```

#### Status Mapping

| Status | Label | Text Color | Background | Border |
|--------|-------|------------|------------|--------|
| `pass` | PASS | `text-mc-green` | `bg-mc-green-muted` | `border-mc-green-border` |
| `warn` | WARN | `text-mc-amber` | `bg-mc-amber-muted` | `border-mc-amber-border` |
| `fail` | FAIL | `text-mc-red` | `bg-mc-red-muted` | `border-mc-red-border` |
| `error` | ERR | `text-mc-red` | `bg-mc-red-muted` | `border-mc-red-border` |
| `skipped` | SKIP | `text-mc-text-3` | `bg-mc-surface-3` | `border-mc-border-1` |

#### Usage

```tsx
import { SeverityTag } from "../ui/SeverityTag";

<SeverityTag status="pass" />   // Renders: PASS in green
<SeverityTag status="fail" />   // Renders: FAIL in red
<SeverityTag status="warn" />   // Renders: WARN in amber
```

---

### 6.4 StatusDot

**File:** `app/src/components/ui/StatusDot.tsx`

A small colored circle with a glow effect used to indicate pass/warn/fail status inline.

#### Props Interface

```typescript
import type { Status } from "../../types"; // "pass" | "warn" | "fail"

interface StatusDotProps {
  status: Status;
  size?: number;  // Diameter in pixels, default 6
}
```

#### Behavior

The dot renders as a solid circle (`border-radius: 50%`) with a matching-color `box-shadow` glow. The glow radius equals the dot's `size` value.

| Status | Fill Color | Glow Color |
|--------|-----------|------------|
| `pass` | `#34d399` | `rgba(52,211,153,0.4)` |
| `warn` | `#fbbf24` | `rgba(251,191,36,0.4)` |
| `fail` | `#f87171` | `rgba(248,113,113,0.5)` |

#### Usage

```tsx
import { StatusDot } from "../ui/StatusDot";

<StatusDot status="pass" />
<StatusDot status="fail" size={8} />
```

---

### 6.5 Section

**File:** `app/src/components/ui/Section.tsx`

A panel container with an optional labeled header. The primary structural component for organizing dashboard content.

#### Props Interface

```typescript
interface SectionProps {
  label?: string;       // Header text (rendered as .mc-label)
  right?: ReactNode;    // Right-aligned header metadata
  children: ReactNode;  // Section body content
  className?: string;   // Additional classes on outer container
}
```

#### Structure

- Outer: `bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden`
- Header (if `label` provided): `px-4 py-[11px] border-b border-mc-border-0`, with label on left and optional `right` content on right
- Body: No default padding (consumer controls layout)

#### Usage

```tsx
import { Section } from "../ui/Section";

<Section label="Quality Gates" right="Last run: 2m ago">
  <div className="p-4">
    {/* Section content */}
  </div>
</Section>

// Without header
<Section>
  <div className="p-4">Plain content panel</div>
</Section>
```

---

### 6.6 Toggle

**File:** `app/src/components/ui/Toggle.tsx`

A boolean switch control with on/off states and an optional locked mode.

#### Props Interface

```typescript
interface ToggleProps {
  on: boolean;       // Current state
  locked?: boolean;  // Prevents interaction, shows disabled style
  onClick?: () => void;
}
```

#### Dimensions

- Track: `38px` wide, `20px` tall, `rounded-[10px]`
- Knob: `14px` diameter, `rounded-full`

#### States

| State | Track | Knob | Border |
|-------|-------|------|--------|
| **Off** | `bg-mc-surface-3` | `bg-mc-text-3`, `left: 3px` | `border-mc-border-1` |
| **On** | `bg-mc-accent` | `bg-white`, `left: 21px` | `border-mc-accent-border` |
| **Locked** | Same as current state | Same as current state | `opacity-60 cursor-not-allowed` |

#### Usage

```tsx
import { Toggle } from "../ui/Toggle";

<Toggle on={isEnabled} onClick={() => setIsEnabled(!isEnabled)} />
<Toggle on={true} locked />
```

---

### 6.7 Select

**File:** `app/src/components/ui/Select.tsx`

A custom dropdown select with keyboard support (Escape to close), click-outside dismiss, and checkmark indicators for the selected option.

#### Props Interface

```typescript
interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  small?: boolean;     // Compact size variant
  disabled?: boolean;
  className?: string;
}
```

#### Sizes

| Size | Trigger Padding | Font Size | Min Width |
|------|----------------|-----------|-----------|
| **Default** | `py-1.5 pl-3 pr-7` | `text-xs` | `80px` |
| **Small** | `py-1 pl-2.5 pr-6` | `text-[10.5px]` | `60px` |

#### Dropdown Styling

- Background: `bg-mc-surface-2`
- Border: `border border-mc-border-1`
- Shadow: `0_8px_24px_rgba(0,0,0,0.4), 0_2px_8px_rgba(0,0,0,0.3)`
- Radius: `rounded-lg`
- Entry animation: `animate-fade-in`
- Selected item: `text-mc-text-0 font-semibold` with purple checkmark
- Hover: `hover:bg-mc-surface-3 hover:text-mc-text-0`

#### Usage

```tsx
import { Select } from "../ui/Select";

const options = [
  { value: "all", label: "All" },
  { value: "pass", label: "Passed" },
  { value: "fail", label: "Failed" },
];

<Select value={filter} onChange={setFilter} options={options} />
<Select value={filter} onChange={setFilter} options={options} small />
```

---

### 6.8 Toast / ToastContainer

**File:** `app/src/components/ui/Toast.tsx`

A notification system with four severity levels, auto-dismiss, and slide-out exit animation. Includes a global imperative API and a React hook.

#### Types

```typescript
type ToastType = "success" | "error" | "warning" | "info";

interface ToastData {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;  // ms, default 4000 (6000 for errors)
}
```

#### ToastContainer Props

```typescript
interface ToastContainerProps {
  toasts: ToastData[];
  onDismiss: (id: string) => void;
}
```

#### Color Mapping

| Type | Background | Border | Icon Background |
|------|-----------|--------|-----------------|
| `success` | `bg-mc-green-muted` | `border-mc-green-border` | `bg-mc-green` |
| `error` | `bg-mc-red-muted` | `border-mc-red-border` | `bg-mc-red` |
| `warning` | `bg-mc-amber-muted` | `border-mc-amber-border` | `bg-mc-amber` |
| `info` | `bg-mc-accent-muted` | `border-mc-accent-border` | `bg-mc-accent` |

#### Toast Styling

- Width: `min-w-[280px] max-w-[400px]`
- Padding: `py-3 px-4`
- Radius: `rounded-lg`
- Shadow: `0_4px_12px_rgba(0,0,0,0.4)`
- Backdrop: `backdrop-blur-sm`
- Exit: slides right (`translateX(100%)`) with `300ms` transition

#### Imperative API

```typescript
import { toast } from "../ui/Toast";

toast.success("Saved", "Changes applied successfully");
toast.error("Build Failed", "3 tests did not pass");
toast.warning("Stale Data", "Last refresh was 10 minutes ago");
toast.info("Hint", "Double-click to edit");
```

#### Hook API

```typescript
import { useToasts, ToastContainer } from "../ui/Toast";

function App() {
  const { toasts, dismiss } = useToasts();
  return <ToastContainer toasts={toasts} onDismiss={dismiss} />;
}
```

---

### 6.9 ConfirmDialog

**File:** `app/src/components/ui/ConfirmDialog.tsx`

A modal confirmation dialog with configurable title, message, and action buttons. Supports a danger variant for destructive operations.

#### Props Interface

```typescript
interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;   // Default: "Confirm"
  cancelLabel?: string;    // Default: "Cancel"
  danger?: boolean;        // Red title text, red border, danger button
  onConfirm: () => void;
  onCancel: () => void;
}
```

#### Structure

- **Backdrop:** `fixed inset-0 bg-black/60 z-[200]`, clicking dismisses
- **Dialog:** `w-[380px] bg-mc-surface-1 rounded-xl border animate-fade-in`
  - Danger variant: `border-mc-red-border`
  - Default variant: `border-mc-border-1`
- **Header:** `px-5 py-4 border-b border-mc-border-0`, title at `text-sm font-bold`
- **Body:** `px-5 py-4 text-[12.5px] leading-relaxed text-mc-text-2`
- **Actions:** `px-5 py-3 border-t border-mc-border-0`, right-aligned with `gap-2`

#### Usage

```tsx
import { ConfirmDialog } from "../ui/ConfirmDialog";

<ConfirmDialog
  title="Delete Project?"
  message="This action cannot be undone. All project data will be permanently removed."
  confirmLabel="Delete"
  danger
  onConfirm={handleDelete}
  onCancel={() => setShowDialog(false)}
/>
```

---

### 6.10 SkeletonLoader

**File:** `app/src/components/ui/SkeletonLoader.tsx`

A family of skeleton loading placeholders for progressive rendering during data fetches. Uses a shimmer gradient animation.

#### Components

**`Skeleton`** -- Base rectangular placeholder.

```typescript
interface SkeletonProps {
  width?: string | number;    // Default: "100%"
  height?: string | number;   // Default: 20
  borderRadius?: number;      // Default: 6
}
```

Renders a `div` with `bg-gradient-to-r from-mc-surface-2 via-mc-surface-3 to-mc-surface-2 bg-[length:200%_100%] animate-shimmer`.

**`SkeletonText`** -- Multiple text-line placeholders. Last line is 70% width.

```typescript
interface SkeletonTextProps {
  lines?: number;  // Default: 3
}
```

**`SkeletonCard`** -- A card-shaped placeholder with icon and text area. Uses `bg-mc-surface-0 border border-mc-border-0 rounded-[10px]`.

**`SkeletonMilestone`** -- A milestone-shaped placeholder with title bar and 4 row items.

**`SkeletonSession`** -- A session-shaped placeholder with 3 two-line entries.

#### Usage

```tsx
import { Skeleton, SkeletonCard, SkeletonMilestone } from "../ui/SkeletonLoader";

// Generic placeholder
<Skeleton width={200} height={16} />

// Loading card
<SkeletonCard />

// Loading milestone list
<SkeletonMilestone />
```

---

### 6.11 Sparkline

**File:** `app/src/components/ui/Sparkline.tsx`

A compact bar-chart SVG for inline data visualization. Renders a fixed-size `64x16` SVG with colored bars.

#### Props Interface

```typescript
interface SparklineProps {
  data: number[];    // Values from 0.0 to 1.0
  color?: string;    // Override color for "full" bars
}
```

#### Bar Colors

Bars are colored based on their value:

| Condition | Color |
|-----------|-------|
| `v >= 1.0` | `color` prop or `#34d399` (green) |
| `v >= 0.5` | `#fbbf24` (amber) |
| `v < 0.5` | `#f87171` (red) |

#### Dimensions

- Canvas: `64px` wide, `16px` tall
- Bar width: `(64 / data.length) - 2px`
- Bar corner radius: `1px`
- Opacity: `0.8`

#### Usage

```tsx
import { Sparkline } from "../ui/Sparkline";

<Sparkline data={[0.2, 0.5, 0.8, 1.0, 0.6, 1.0]} />
<Sparkline data={[1, 1, 0.5, 0.3]} color="#8b7cf6" />
```

---

### 6.12 InlineMarkdown

**File:** `app/src/components/ui/InlineMarkdown.tsx`

Renders basic inline Markdown formatting within a `<span>`. Supports bold, italic, and inline code.

#### Props Interface

```typescript
interface InlineMarkdownProps {
  children: string;    // Raw markdown string
  className?: string;
}
```

#### Supported Syntax

| Markdown | Rendered As | Styling |
|----------|------------|---------|
| `**text**` or `__text__` | `<strong>` | `font-bold` |
| `*text*` or `_text_` | `<em>` | `italic` |
| `` `code` `` | `<code>` | `font-mono text-[0.9em] px-[5px] py-px rounded bg-mc-surface-3 text-mc-text-1` |

#### Usage

```tsx
import { InlineMarkdown } from "../ui/InlineMarkdown";

<InlineMarkdown>{"This is **bold** and `code` and *italic*."}</InlineMarkdown>
```

---

### 6.13 DiffBlock

**File:** `app/src/components/ui/DiffBlock.tsx`

Renders unified diff text with syntax-aware line coloring.

#### Props Interface

```typescript
interface DiffBlockProps {
  text: string;         // Raw unified diff text
  maxHeight?: number;   // Scroll container max height, default 300
}
```

#### Exports

- **`DiffBlock`** -- The rendering component.
- **`looksLikeDiff(text: string): boolean`** -- Utility that returns `true` if the text contains 2+ diff markers (`diff --git`, `@@`, `+++`, `---`).

#### Line Coloring

| Line Prefix | Color Class |
|-------------|-------------|
| `diff --git` | `text-mc-text-3 font-bold` |
| `@@` | `text-mc-cyan` |
| `+++` or `---` | `text-mc-text-3` |
| `+` (addition) | `text-mc-green` |
| `-` (deletion) | `text-mc-red` |
| Other | `text-mc-text-2` |

#### Styling

- Container: `<pre>` with `font-mono text-[10.5px] leading-[1.55]`
- Background: `bg-mc-bg border border-mc-border-0 rounded-lg p-3`
- Overflow: `overflow-x-auto overflow-y-auto whitespace-pre-wrap break-words`
- Empty lines render as `\u00A0` (non-breaking space) to preserve vertical rhythm

#### Usage

```tsx
import { DiffBlock, looksLikeDiff } from "../ui/DiffBlock";

if (looksLikeDiff(output)) {
  return <DiffBlock text={output} maxHeight={400} />;
}
```

---

## 7. Animation Patterns

All keyframes are defined in both `global.css` and `tailwind.config.js`. Use Tailwind `animate-*` classes when possible; use `@keyframes` names directly only for custom inline `animation` properties.

### 7.1 Entry Animations

| Animation | Tailwind Class | Duration | Easing | Effect |
|-----------|---------------|----------|--------|--------|
| **Fade In** | `animate-fade-in` | 300ms | ease | Fade in + translate Y from -4px |
| **Fade In (fast)** | `animate-fade-in-fast` | 200ms | ease | Same as above, faster |
| **Fade In (fastest)** | `animate-fade-in-fastest` | 150ms | ease | Same as above, fastest |
| **Slide Up** | `animate-slide-up` | 200ms | ease | Fade in + translate Y from +6px |
| **Slide In** | `animate-slide-in` | 250ms | ease | Fade in + translate X from +20px |
| **Scale In** | `animate-scale-in` | 200ms | ease-out | Fade in + scale from 0.95 |

### 7.2 Looping Animations

| Animation | Tailwind Class / CSS | Duration | Effect |
|-----------|---------------------|----------|--------|
| **Pulse** | `animate-pulse` | 2s, infinite | Opacity oscillates 1.0 to 0.7, scale 1.0 to 1.1 |
| **Shimmer** | `animate-shimmer` | 1.5s, infinite | Background position sweeps left (for skeleton loading) |
| **cc-spin** | `animation: cc-spin 1s linear infinite` | 1s, infinite | 360-degree rotation (for loading spinners) |
| **cc-pulse** | `animation: cc-pulse 2s ease-in-out infinite` | 2s, infinite | Opacity oscillates 1.0 to 0.4 (softer pulse) |
| **cc-blink** | `animation: cc-blink 1s step-end infinite` | 1s, infinite | Opacity toggles 1.0 to 0.0 (cursor-style blink) |
| **spin** | `animation: spin 1s linear infinite` | 1s, infinite | Simple 360-degree rotation (Tailwind-compatible) |

### 7.3 Transition Patterns

Components use CSS transitions for interactive state changes:

| Property | Duration | Usage |
|----------|----------|-------|
| `transition-all` | Default (150ms) | Buttons (general), toggles |
| `transition-transform duration-150` | 150ms | Chevron rotation in Select and accordion headers |
| `transition-all duration-200` | 200ms | Toggle track and knob |
| `transition-all duration-300 ease-out` | 300ms | Toast entry/exit |
| `transition-[border-color,background] duration-150` | 150ms | Select trigger hover |
| `transition-[background,color] duration-100` | 100ms | Select dropdown option hover |

### 7.4 Toast Exit Animation

Toast dismissal is handled via inline styles rather than CSS classes:

```css
/* Exit state (applied via style prop) */
opacity: 0;
transform: translateX(100%);
transition: all 300ms ease-out;
```

The exit animation begins 300ms before the toast is removed from the DOM, allowing the slide-out to complete before unmounting.

---

## 8. Icon System

**File:** `app/src/components/ui/Icons.tsx`

Icons are inline SVGs exported as a single `Icons` object. Each icon is a function component that accepts `size` and `color` props.

### 8.1 Icon Props

```typescript
interface IconProps {
  size?: number;    // Width and height in pixels (default varies per icon)
  color?: string;   // Fill or stroke color (default: "currentColor")
}
```

Using `currentColor` as the default means icons inherit their color from the parent element's `color` or Tailwind `text-*` class.

### 8.2 Available Icons

| Icon | Default Size | Style | Description |
|------|-------------|-------|-------------|
| `Icons.play` | 10px | Filled | Right-pointing triangle (play/run) |
| `Icons.check` | 10px | Stroked | Checkmark (selected, complete) |
| `Icons.chevDown` | 10px | Stroked | Downward chevron with `open` prop for 180-degree rotation |
| `Icons.edit` | 10px | Stroked | Pencil (edit action) |
| `Icons.x` | 10px | Stroked | X / close mark (dismiss, cancel) |
| `Icons.alert` | 12px | Stroked + Filled | Triangle with exclamation (warning) |
| `Icons.branch` | 12px | Stroked | Git branch diagram (branching, version control) |
| `Icons.refresh` | 12px | Stroked | Circular arrows (refresh, reload) |
| `Icons.retry` | 10px | Stroked | Circular arrows, smaller (retry action) |
| `Icons.lock` | 12px | Stroked + Filled | Padlock (locked, security) |
| `Icons.folder` | 13px | Stroked | Folder shape (file system, project) |
| `Icons.bolt` | 11px | Filled | Lightning bolt (quick action, automation) |
| `Icons.arrow` | 10px | Stroked | Right-pointing arrow (navigation, proceed) |
| `Icons.search` | 12px | Stroked | Magnifying glass (search) |

### 8.3 Special: `chevDown` with `open` prop

The `chevDown` icon accepts an additional `open?: boolean` prop that rotates it 180 degrees when `true`, with a `150ms` CSS transition. This is used in Select components and accordion headers.

```typescript
Icons.chevDown({ size: 10, open: isExpanded })
```

### 8.4 Usage

```tsx
import { Icons } from "../ui/Icons";

// Inline in JSX
<Icons.play size={12} color="#34d399" />

// Inherits color from parent
<span className="text-mc-accent">
  <Icons.check size={14} />
</span>

// In a button
<Button small>
  <Icons.refresh size={10} /> Refresh
</Button>
```

---

## 9. Styling Rules and Best Practices

### 9.1 Tailwind Classes over Inline Styles

Always prefer Tailwind `mc-*` classes for styling. Import `t` from `tokens.ts` only when Tailwind classes cannot be applied:

- SVG `fill` and `stroke` attributes
- Computed values that depend on runtime data (e.g., `StatusDot` glow)
- Dynamic `style` objects with calculated properties

```tsx
// Correct: Tailwind class
<div className="bg-mc-surface-1 text-mc-text-0">

// Correct: Token import for SVG
<path fill={t.green} />

// Incorrect: Token import for background
<div style={{ background: t.surface1 }}>
```

### 9.2 Semantic Color Usage

Colors carry meaning. Do not use status colors for decoration.

| Color | Meaning | Never Use For |
|-------|---------|---------------|
| Green | Success, pass, addition, complete | Branding, links, decorative elements |
| Red | Error, failure, danger, deletion | Non-destructive warnings |
| Amber | Warning, caution, medium severity | Success indicators |
| Cyan | Informational, branch-related, diff headers | Error states |
| Accent (purple) | Interactive, selected, brand, primary action | Status indicators |

### 9.3 Surface Layering

Each level of nesting should increase the surface number:

```
bg-mc-bg          -> Page background
  bg-mc-surface-0  -> Cards within page (used in skeleton cards)
  bg-mc-surface-1  -> Sections, panels, dialogs
    bg-mc-surface-2  -> Inputs, tags, dropdowns inside sections
      bg-mc-surface-3  -> Hover states, active states inside inputs
```

Do not skip levels. Do not use `surface-3` directly on the page background.

### 9.4 Border Usage

- Use `border-mc-border-0` for structural dividers (section separators, card borders)
- Use `border-mc-border-1` for interactive element borders (inputs, toggles, dropdowns)
- Use `border-mc-border-2` for emphasis borders (ghost button outlines)
- Use semantic borders (`border-mc-red-border`, etc.) only with matching semantic backgrounds

### 9.5 Text Hierarchy

Apply text colors consistently to maintain visual hierarchy:

- `text-mc-text-0`: Primary content the user should read first (headings, titles, names)
- `text-mc-text-1`: Supporting content that is still important (body text, descriptions)
- `text-mc-text-2`: Secondary metadata (timestamps, counts, muted descriptions)
- `text-mc-text-3`: Tertiary information (labels, section identifiers, disabled text)

### 9.6 Monospace vs Sans-Serif

- **Monospace (`font-mono`):** Labels (`.mc-label`), tags (`.mc-tag`, `.mc-severity-tag`), code, file paths, timestamps, numerical data, select options, section metadata
- **Sans-serif (`font-sans`):** Buttons, dialog text, toast content, prose descriptions, error messages

### 9.7 Component Composition

When building new components:

1. Use `Section` as the outer container for any dashboard panel
2. Use `Tag` or `SeverityTag` for inline status labels
3. Use `Button` for all interactive actions -- never create custom button styles
4. Use `StatusDot` for inline pass/warn/fail indicators in lists
5. Use `Skeleton*` components as loading placeholders
6. Use `ConfirmDialog` for all destructive action confirmations
7. Use `toast.*` for transient feedback after async operations
8. Use `Select` instead of native `<select>` elements
9. Use `Toggle` instead of native checkboxes for boolean settings
10. Use `Icons.*` instead of external icon libraries or emoji

### 9.8 Responsive Considerations

Claudetini is a desktop application (Tauri). There is no mobile breakpoint. The minimum expected viewport is approximately 1024px wide. Components are designed for a fixed desktop layout and do not need mobile adaptations.

### 9.9 Accessibility Notes

- All buttons accept a `title` prop for native tooltips
- Interactive elements use `cursor-pointer`; disabled elements use `cursor-not-allowed`
- Disabled state is communicated via `opacity-50` (buttons) or `opacity-60` (toggles, selects)
- The `ConfirmDialog` backdrop is clickable to dismiss
- The `Select` dropdown closes on `Escape` key press
- Color is not the sole indicator of meaning -- `SeverityTag` includes text labels alongside colors

### 9.10 z-index Scale

| z-index | Usage |
|---------|-------|
| `1000` | Select dropdown menus |
| `200` | ConfirmDialog backdrop and modal |
| `9999` | Toast container |

Keep toast notifications above all other overlays. Dialogs sit below toasts but above all page content. Dropdowns are above page content but below modals.
