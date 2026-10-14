# PyInstaller spec: a single portable Windows executable (unpacks to a temp folder at start).
# Run from the repository root:  pyinstaller packaging/redactor-portable.spec --noconfirm
import re
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "redactor"
tessdata = PKG / "resources" / "tessdata"
if not (tessdata / "eng.traineddata").is_file():
    raise SystemExit("tessdata missing: run `python scripts/fetch_tessdata.py` first")
VERSION = re.search(r'__version__ = "([^"]+)"', (PKG / "__init__.py").read_text()).group(1)

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(PKG / "i18n" / "*.json"), "redactor/i18n"),
        (str(PKG / "resources" / "icons"), "redactor/resources/icons"),
        (str(PKG / "resources" / "app.png"), "redactor/resources"),
        (str(tessdata / "*.traineddata"), "redactor/resources/tessdata"),
    ],
    hiddenimports=["PySide6.QtSvg"],
    excludes=[
        "tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
        "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtNetwork", "PySide6.QtSql",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"Redactor-{VERSION}-windows-x64-portable",
    console=False,
    icon=str(ROOT / "packaging" / "icon.png"),
    upx=False,
)
