# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop (Qt / PySide6 on Windows, macOS, Linux). Not web, iOS or Android.

## Stack

Python 3.12, PySide6 (Qt Widgets, Fusion style), PyMuPDF for PDF parsing, redaction and OCR (bundled tessdata). Packaged with PyInstaller; installers built by GitHub Actions.

## Users

General use: the author and anyone who must publish or send a PDF with parts permanently removed. No specific profession assumed. Typically works in the evening, in a dim room, on one document at a time.

## Product Purpose

Open a PDF, mark text or areas (by mouse selection, rectangle, search / data patterns such as PESEL, NIP, IBAN, or after OCR of scans), and export a new PDF in which the marked content is physically gone and unrecoverable, together with metadata, attachments, scripts and hidden text. Success means the user holds a verification report proving it.

## Positioning

Successor in spirit to `pdf-redact-tools` (rasterize → flatten → strip metadata), but interactive: true content redaction by default, full rasterization as an optional paranoid mode, and an automatic re-read of the output that proves the removal.

## Capabilities and Constraints

- The original file is never written to; export always targets a different path.
- Marks are pending until export; the output is verified automatically after saving.
- Project files (`*.redactor.json`) store marks but not the redacted text unless the user opts in.
- UI languages: Polish and English, with a checker that proves translation completeness.
- License: AGPL-3.0-or-later (PyMuPDF).

## Brand Commitments

- Name: **Redactor**.
- Look and feel explicitly requested by the user: like Photoshop. Dark charcoal professional tool, left tool strip, contextual options bar, dockable panels on the right, precise and responsive interaction. Must never look toy-like or web-like.

## Product Principles

1. Proof over promise: show what was verified, never just "done".
2. The original is sacred: no code path writes to the source file.
3. Pending vs. applied must be impossible to confuse.
4. Keyboard-fast review: dozens of pattern hits are accepted or rejected without the mouse.
5. Safe defaults; paranoia (flattening) one click away.

## Accessibility & Inclusion

Full keyboard operation, visible focus states, tooltips with shortcuts, contrast sufficient on dark theme; light theme available.
