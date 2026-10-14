"""Convert packaging/icon.png into build/icon.ico for the Windows installer."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / "build" / "icon.ico"
out.parent.mkdir(exist_ok=True)
Image.open(ROOT / "packaging" / "icon.png").save(out, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
print(out)
