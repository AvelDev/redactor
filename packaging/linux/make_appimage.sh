#!/usr/bin/env bash
# Turn the PyInstaller folder build into an AppImage.
set -euo pipefail
VERSION="${1:?version}"
APPDIR="build/Redactor.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -R dist/Redactor/. "$APPDIR/usr/bin/"
cp packaging/linux/redactor.desktop "$APPDIR/redactor.desktop"
cp packaging/icon.png "$APPDIR/redactor.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/Redactor" "$@"
RUN
chmod +x "$APPDIR/AppRun"
TOOL="build/appimagetool"
if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    https://github.com/AppImage/appimagetool/releases/download/1.9.0/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "dist/Redactor-$VERSION-linux-x86_64.AppImage"
