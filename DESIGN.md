---
name: Redactor
description: Permanent, verifiable PDF redaction in a dark graphite studio.
colors:
  pasteboard: "#1c1c1e"
  panel: "#29292b"
  panel-header: "#313134"
  raised: "#3a3a3d"
  raised-hover: "#454549"
  field: "#1f1f21"
  hairline: "#151517"
  control-border: "#48484c"
  text: "#e6e6e8"
  text-dim: "#aeaeb3"
  text-faint: "#94949a"
  accent: "#3b82f6"
  accent-hover: "#5b97f8"
  on-accent: "#ffffff"
  pending-redaction: "#ff5a36"
  search-hit: "#f5b83d"
  ok: "#46c35a"
  warn: "#e3a72f"
  fail: "#ff5d55"
typography:
  body:
    fontFamily: "system UI sans (Segoe UI / SF Pro / platform default)"
    fontSize: "12px"
    fontWeight: 400
  label-strong:
    fontFamily: "system UI sans"
    fontSize: "12px"
    fontWeight: 600
  dialog-title:
    fontFamily: "system UI sans"
    fontSize: "15px"
    fontWeight: 600
  mono-data:
    fontFamily: "Cascadia Mono, SF Mono, Menlo, Consolas, DejaVu Sans Mono, monospace"
    fontSize: "12px"
rounded:
  control: "2px"
  button: "3px"
  surface: "4px"
spacing:
  tight: "4px"
  control: "8px"
  panel: "10px"
  dialog: "18px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.button}"
    padding: "5px 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "5px 14px"
  input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "3px 6px"
  tool-button-checked:
    backgroundColor: "{colors.raised-hover}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
  panel-tab-selected:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    padding: "5px 12px"
---

# Design System: Redactor

## Overview

**Creative North Star: "The Retoucher's Studio"**

Redactor looks and handles like a professional image editor, as the user asked when they said it should look like Photoshop. A dark graphite workspace recedes so that the white page carries the light. Tools sit in a narrow left strip with single-key shortcuts. A contextual options bar changes with the active tool, and panels dock on the right. Density is high and nothing is decorative: every colour, outline and motion signals a state.

Two promises shape the system. Pending vs. applied must be impossible to confuse, and the user receives proof rather than reassurance. They show up as a reserved signal colour for pending redactions, a solid-fill preview of the result, and a checklist report after export. The system rejects the web-app vocabulary: dashed upload cards, oversized headings, gradients and glassy surfaces.

The light theme is a token variant of the same structure, not a different design (`LIGHT` in `src/redactor/ui/theme.py`).

**Key Characteristics:**
- Four-step graphite neutral ladder; input fields sunk below the panel.
- One blue accent, spent only on selection, focus and the primary action.
- A red-orange that means exactly one thing: "this will be removed".
- System UI sans at 12 px, tabular figures for every counter.
- Lucide outline icons, tinted from tokens per state.

## Colors

Restrained: neutrals carry the surface, one accent carries action, and three semantic hues carry state.

- **Pasteboard** `#1c1c1e`: the canvas ground behind pages and the empty state.
- **Panel / Header / Raised** `#29292b` / `#313134` / `#3a3a3d`: docks and toolbars, panel title bars and tab strips, buttons and checked tools. Raised-hover `#454549`.
- **Field** `#1f1f21`: text inputs sit *below* the panel, as in Photoshop.
- **Hairline** `#151517`: the 1 px separation between regions. Control borders use `#48484c`.
- **Accent** `#3b82f6`: selection outlines and handles, focus rings, primary buttons, progress. Selected list rows use a muted blend of the accent into the panel (`selection()` in theme.py) so normal text and icons stay legible in both themes.
- **Pending redaction** `#ff5a36`: only for marks awaiting export.
- **Search hit** `#f5b83d`: only for unreviewed search and pattern candidates.
- **OK / Warn / Fail** `#46c35a` / `#e3a72f` / `#ff5d55`: only in the verification report and validation errors.

## Typography

One family, the platform's UI sans, at a dense fixed scale with no fluid sizing.

- Body and labels: 12 px regular. Section titles in panels: 12 px semibold in `text-dim`.
- Dialog and report titles: 15 px semibold.
- Counters, page numbers, zoom and mark counts use tabular figures (`theme.tabular()`).
- Monospace only for data that is data: SHA-256 hashes and verification details.

## Layout

The Photoshop grammar, fixed across all documents:

- **Left tool strip** (~40 px): Hand `H`, Select Text `T`, Rectangle `R`, Zoom `Z`, then a separator, Search `S`, OCR `O`.
- **Options bar** on top: icon and name of the active tool, its options, hint text, and on the right Preview Result plus the primary Export button.
- **Document tabs** titled `name.pdf @ 125% *` with a lock icon (the original is read-only).
- **Canvas**: pages stacked vertically with an 18 pt gap and 36 pt margins on the pasteboard.
- **Right dock**: Properties on top; Marks / Search / Pages as compact tabs mounted at the top of the area below. Docks can be moved but not floated or closed.
- **Status bar**: message on the left; page, zoom, mark count and "Original: read-only" as permanent cells on the right; "No document" when empty.

## Elevation & Depth

The interface is flat and uses tonal layering instead of shadows. The single exception is the page itself: six 1-device-pixel black layers at 7 % opacity, offset slightly downwards, so the sheet lifts off the pasteboard. Dialogs rely on the window system for elevation.

## Shapes

Corners are nearly square: 2 px for fields, 3 px for buttons and tool buttons, 4 px for report surfaces. Borders are 1 px. Overlays on the canvas use cosmetic (zoom-independent) pens so outlines stay one device pixel at any zoom.

## Components

- **Pending mark**: translucent red-orange fill (10 %, 16 % on hover), cosmetic diagonal hatch lines every 4 device px at 75 %, and a crisp 1 px edge (1.5 px on hover).
- **Selected mark**: accent outline 1.5 px offset by 2 device px. A single rectangle mark also gets eight white handles with an accent edge.
- **Preview / exported look**: solid fill in the mark's colour, with the optional label centred in a contrasting colour.
- **Search candidate**: amber dashed outline with a 10 % fill. The current candidate is solid with a 28 % fill.
- **Marquee**: red-orange edge, with a live `W × H mm` readout in a header-coloured tag beside the cursor.
- **Tool button**: transparent at rest, raised on hover, raised-hover with a control border when checked. Icons are dim at rest and bright when hovered or checked.
- **Primary button**: accent fill, white semibold text. There is at most one per surface (Export in the options bar, Export and Verify / Close in dialogs).
- **Verification report**: a header frame with a 32 px status icon and a green or red border, then rows of 18 px Lucide status icons (circle-check / circle-alert / circle-x / info) with detail text.
- **Empty state**: bare pasteboard with the app icon, one line of heading, the Open PDF button, the "original is never changed" promise and a recent-files list. The drop target only shows an accent border while a file is dragged over it.

## Do's and Don'ts

- **Do** keep red-orange exclusively for pending redactions and amber exclusively for unreviewed hits.
- **Do** give every new tool a single-letter shortcut and show it in the tooltip.
- **Do** show proof (what was checked, with icons) after any operation that claims data is gone.
- **Do** run `scripts/check_translations.py` after adding UI text; every string goes through `tr()` / `tr_n()` / `N_()`.
- **Don't** use the accent for decoration or for inactive states.
- **Don't** introduce modal dialogs for tasks that can live in a panel. Export is modal because it is a deliberate, consequential step.
- **Don't** use Unicode glyphs or emoji in place of icons; add the Lucide SVG to `resources/icons/` instead.
- **Don't** offer any path that writes to the opened source file.
