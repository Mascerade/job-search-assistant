# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Job Search Assistant
**Generated:** 2026-11-26 09:27:14
**Category:** Job Board/Recruitment
**Token files:** `tokens.json` (W3C Design Tokens Community Group JSON).
**CSS variables:** `tokens.css` (`:root` custom properties).
Token files are master-level only; `--page` overrides do not emit tokens.
**Design Dials:** Variance 3/10 (Centered / Minimal) | Motion 3/10 (Subtle) | Density 7/10 (Standard)

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Primary | `#0369A1` | `--color-primary` |
| On Primary | `#FFFFFF` | `--color-on-primary` |
| Secondary | `#0EA5E9` | `--color-secondary` |
| On Secondary | `#0F172A` | `--color-on-secondary` |
| Accent/CTA | `#16A34A` | `--color-accent` |
| On Accent/CTA | `#000000` | `--color-on-accent` |
| Background | `#F0F9FF` | `--color-background` |
| Foreground | `#0C4A6E` | `--color-foreground` |
| Card | `#FFFFFF` | `--color-card` |
| Card Foreground | `#0C4A6E` | `--color-card-foreground` |
| Muted | `#E7EFF5` | `--color-muted` |
| Muted Foreground | `#475569` | `--color-muted-foreground` |
| Border | `#BAE6FD` | `--color-border` |
| Destructive | `#DC2626` | `--color-destructive` |
| On Destructive | `#FFFFFF` | `--color-on-destructive` |
| Ring | `#0369A1` | `--color-ring` |

**Color Notes:** Professional blue + success green [Accent adjusted from #22C55E]

### Typography

- **Heading Font:** Fira Code
- **Body Font:** Fira Sans
- **Mood:** dashboard, data, analytics, code, technical, precise
- **Google Fonts:** [Fira Code + Fira Sans](https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
```

### Spacing Variables

*Density: 7/10 — Standard*

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | Hero images, featured cards |

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: #16A34A;
  color: #000000;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: #0369A1;
  border: 2px solid #0369A1;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: #F0F9FF;
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-md);
  transition: all 200ms ease;
  cursor: pointer;
}

.card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
```

### Inputs

```css
.input {
  padding: 12px 16px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: #0369A1;
  outline: none;
  box-shadow: 0 0 0 3px #0369A120;
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.modal {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Minimalism & Swiss Style

**Keywords:** Clean, simple, spacious, functional, white space, high contrast, geometric, sans-serif, grid-based, essential

**Best For:** Enterprise apps, dashboards, documentation sites, SaaS platforms, professional tools

**Key Effects:** Subtle hover (200-250ms), smooth transitions, sharp shadows if any, clear type hierarchy, fast loading

### Page Pattern

**Pattern Name:** Funnel (3-Step Conversion)

- **Conversion Strategy:** Progressive disclosure. Show only essential info per step. Use progress indicators. Multiple CTAs.
- **CTA Placement:** Each step: mini-CTA. Final: main CTA
- **Section Order:** Hero > Step 1 (problem) > Step 2 (solution) > Step 3 (action) > CTA progression

---

## Motion

**Scroll Reveal** (Subtle) — Trigger: scroll (viewport enter) | Duration: 300-400ms | Easing: `power1.out`

```js
gsap.from(el, { opacity: 0, y: 12, duration: 0.35, ease: 'power1.out', scrollTrigger: { trigger: el, start: 'top 90%', toggleActions: 'play none none reverse' } });
```

**Framework notes:** Requires the ScrollTrigger plugin registered once via gsap.registerPlugin(ScrollTrigger); Use matchMedia('(prefers-reduced-motion: reduce)') to skip non-essential motion and render the final state immediately

- ✅ Keep the y offset small (8-16px) so it reads as a fade, not a slide
- ❌ Don't reveal below-the-fold content needed for SEO/crawlers as invisible-by-default without a no-JS fallback
- ⚡ toggleActions 'play none none reverse' avoids re-triggering on every scroll direction change

---

## Anti-Patterns (Do NOT Use)

- ❌ Outdated forms
- ❌ Hidden filters

### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile

---

## Project Adaptations (override the generated rules above)

These decisions were made deliberately for this app; they win over anything above.

1. **Headings use Fira Sans, not Fira Code.** Fira Code is used only for numbers that should align
   (fit scores, costs, dates, counts) via `font-mono tabular-nums`.
2. **No landing-page "Funnel" pattern.** This is an app: sidebar (desktop) / bottom bar (mobile) + list/detail views.
3. **No GSAP.** Motion is CSS transitions only: 150–250ms, `ease-out`, transform/opacity only, and disabled under
   `prefers-reduced-motion`.
4. **Secondary (`#0EA5E9`) is never used as text in light mode** (2.77:1 on white). Use it for fills, chart marks,
   and decoration; text on it uses `--color-on-secondary`.
5. **Status is never color-only.** Every application status = color + Lucide icon + text label.
6. **Every drag interaction has a click alternative** ("Move to…" menu) — WCAG 2.2 dragging movements.

### Dark mode palette (all text pairs verified ≥ 4.5:1)

| Role | Hex | Contrast check |
|------|-----|----------------|
| Background | `#0B1220` | fg 16.3:1, muted-fg 7.3:1 |
| Foreground | `#E0F2FE` | |
| Card | `#111A2E` | fg 15.1:1 |
| Muted | `#1E293B` | muted-fg 5.7:1 |
| Muted Foreground | `#94A3B8` | |
| Border | `#1E3A5F` | |
| Primary | `#38BDF8` | on-primary `#0B1220` 8.7:1; as text on card 8.1:1 |
| Secondary | `#7DD3FC` | as text on card 10.4:1 |
| Accent/CTA | `#22C55E` | on-accent `#052E16` 6.5:1 |
| Destructive | `#F87171` | on-destructive `#0B1220` 6.8:1 |
| Ring | `#38BDF8` | |

Light-mode pairs verified: fg/bg 8.9:1, muted-fg/muted 6.5:1, on-primary/primary 5.9:1,
on-accent/accent 6.4:1, on-destructive/destructive 4.8:1.
