"""Render the main window in its key states to PNG files (design review / docs).

Usage: python scripts/screenshots.py [out_dir] [--lang pl|en] [--theme dark|light]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent


def sample_pdf(path: Path) -> Path:
    """A realistic two-page letter with personal data, plus a scanned page."""
    doc = pymupdf.open()
    page = doc.new_page()
    y = 90
    lines = [
        ("Umowa najmu lokalu mieszkalnego nr 14/2026", 15),
        ("", 11),
        ("Zawarta w Krakowie dnia 3 marca 2026 r. pomiędzy:", 11),
        ("Wynajmującym: Anna Nowak, zam. ul. Długa 12/4, 31-147 Kraków,", 11),
        ("PESEL 44051401458, tel. +48 600 123 456, e-mail anna.nowak@example.com", 11),
        ("a Najemcą: Piotr Wiśniewski, NIP 123-456-32-18, dowód osobisty ABA300000.", 11),
        ("", 11),
        ("§1. Wynajmujący oddaje Najemcy w najem lokal o powierzchni 48 m².", 11),
        ("§2. Czynsz w wysokości 2 400 zł płatny jest na rachunek", 11),
        ("PL61 1090 1014 0000 0712 1981 2874 do 10. dnia każdego miesiąca.", 11),
        ("§3. Kaucja zwrotna wynosi 4 800 zł i zostanie zwrócona po zakończeniu umowy.", 11),
        ("§4. Umowa zostaje zawarta na czas określony 12 miesięcy.", 11),
        ("", 11),
        ("Kontakt w sprawach technicznych: administrator@example.com", 11),
    ]
    fonts = [Path(p) for p in ("C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
                                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    fontfile = next((str(f) for f in fonts if f.exists()), None)
    font = pymupdf.Font(fontfile=fontfile) if fontfile else pymupdf.Font("helv")
    writer = pymupdf.TextWriter(page.rect)
    for text, size in lines:
        writer.append((64, y), text, font=font, fontsize=size)
        y += size * 1.9
    writer.write_text(page)
    page2 = doc.new_page()
    src = pymupdf.open()
    sp = src.new_page(width=420, height=180)
    sp.insert_text((20, 60), "Oswiadczenie Najemcy", fontsize=20)
    sp.insert_text((20, 110), "Podpisano: Piotr Wisniewski", fontsize=16)
    page2.insert_image(pymupdf.Rect(64, 80, 484, 260), pixmap=sp.get_pixmap(dpi=150))
    doc.save(path)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=str(ROOT / ".impeccable" / "review"))
    ap.add_argument("--lang", default="pl")
    ap.add_argument("--theme", default="dark")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QSettings, QTimer

    tmp = Path(tempfile.mkdtemp())
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)

    from redactor import i18n
    from redactor.app import create_app

    app, settings = create_app(sys.argv[:1])
    settings.setValue("language", args.lang)
    settings.setValue("theme", args.theme)
    i18n.set_language(args.lang)
    from redactor.ui import theme

    theme.apply(app, args.theme)
    from redactor.core.textops import scan_query
    from redactor.ui.main_window import MainWindow

    win = MainWindow(settings)
    win.resize(1440, 900)
    win.show()

    def grab(name: str) -> None:
        app.processEvents()
        for _ in range(6):
            app.processEvents()
        win.grab().save(str(out / f"{name}.png"))
        print("saved", out / f"{name}.png")

    def run() -> None:
        grab("empty")
        pdf = sample_pdf(tmp / "umowa-najmu.pdf")
        s = win.open_path(pdf)
        app.processEvents()
        c = win.canvas
        c.set_zoom(1.0)
        c.go_to_page(0)
        s.add(scan_query(s.doc, [0], "Anna Nowak", regex=False, case_sensitive=True))
        win.search_panel.pattern_boxes["pattern.postal_code"].setChecked(True)
        win.search_panel.search_patterns()
        win.d_search.raise_()
        QTimer.singleShot(400, after_search)

    def after_search() -> None:
        grab("search-review")
        win.search_panel.accept_all()
        from redactor.core.marks import Mark, MarkKind

        area = Mark(page=0, rects=((60, 405, 330, 425),), kind=MarkKind.AREA)
        win.session.add([area])
        win.session.select([area.id])
        win.d_marks.raise_()
        QTimer.singleShot(400, after_marks)

    def after_marks() -> None:
        grab("document-marks")
        win.a_preview.setChecked(True)
        QTimer.singleShot(400, after_preview)

    def after_preview() -> None:
        grab("preview")
        win.a_preview.setChecked(False)
        from redactor.ui.export_dialog import ExportDialog

        dlg = ExportDialog(win.session, 0, win)
        dlg.set_output(tmp / "umowa-najmu-redacted.pdf")
        dlg.show()

        def shot_setup() -> None:
            app.processEvents()
            dlg.grab().save(str(out / "export-setup.png"))
            print("saved export-setup")
            dlg._export()
            QTimer.singleShot(2500, shot_report)

        def shot_report() -> None:
            app.processEvents()
            dlg.grab().save(str(out / "export-report.png"))
            print("saved export-report")
            dlg.close()
            win.session.undo.setClean()
            win.close()
            app.quit()

        QTimer.singleShot(600, shot_setup)

    QTimer.singleShot(300, run)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
