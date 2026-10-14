"""Application bootstrap: settings, language, theme, main window."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from redactor import __version__, i18n
from redactor.ui import theme


def create_app(argv: list[str]) -> tuple[QApplication, QSettings]:
    app = QApplication.instance()
    if app is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(argv)
    app.setApplicationName("Redactor")
    app.setOrganizationName("Redactor")
    app.setApplicationVersion(__version__)
    settings = QSettings()
    i18n.set_language(str(settings.value("language", i18n.system_language())))
    theme.apply(app, str(settings.value("theme", "dark")))
    app.setWindowIcon(QIcon(str(theme.ICON_DIR.parent / "app.png")))
    return app, settings


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--self-test" in argv:
        from redactor.selftest import main as selftest

        return selftest()
    app, settings = create_app(argv)
    from redactor.ui.main_window import MainWindow

    window = MainWindow(settings)
    window.show()
    for path in argv[1:]:
        window.open_path(path)
    return app.exec()
