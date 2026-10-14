# PyInstaller spec: one folder build on every OS, plus a .app bundle on macOS.
# Run from the repository root:  pyinstaller packaging/redactor.spec --noconfirm
import sys
import re
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "redactor"
tessdata = PKG / "resources" / "tessdata"
if not (tessdata / "eng.traineddata").is_file():
    raise SystemExit("tessdata missing: run `python scripts/fetch_tessdata.py` first")

datas = [
    (str(PKG / "i18n" / "*.json"), "redactor/i18n"),
    (str(PKG / "resources" / "icons"), "redactor/resources/icons"),
    (str(PKG / "resources" / "app.png"), "redactor/resources"),
    (str(tessdata / "*.traineddata"), "redactor/resources/tessdata"),
]

excluded = [
    "tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtNetwork", "PySide6.QtSql",
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    excludes=excluded,
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = str(ROOT / "packaging" / "icon.png")
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Redactor",
    console=False,
    icon=icon,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Redactor", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Redactor.app",
        icon=icon,
        bundle_identifier="org.redactor.Redactor",
        info_plist={
            "CFBundleShortVersionString": re.search(r'__version__ = "([^"]+)"', (PKG / "__init__.py").read_text()).group(1),
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [
                {"CFBundleTypeName": "PDF", "CFBundleTypeRole": "Viewer", "LSItemContentTypes": ["com.adobe.pdf"]}
            ],
        },
    )
