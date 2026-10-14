"""Download Tesseract language data (tessdata_fast) into the package resources."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

TAG = "4.1.0"
LANGS = ("eng", "pol")
URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/{tag}/{lang}.traineddata"
TARGET = Path(__file__).resolve().parent.parent / "src" / "redactor" / "resources" / "tessdata"


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        dest = TARGET / f"{lang}.traineddata"
        if dest.is_file() and dest.stat().st_size > 0:
            print(f"{lang}: present")
            continue
        url = URL.format(tag=TAG, lang=lang)
        print(f"{lang}: downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
        dest.write_bytes(data)
        print(f"{lang}: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
