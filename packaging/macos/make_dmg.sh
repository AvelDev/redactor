#!/usr/bin/env bash
# Wrap dist/Redactor.app into a compressed disk image.
set -euo pipefail
VERSION="${1:?version}"
STAGE="$(mktemp -d)"
cp -R dist/Redactor.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Redactor $VERSION" -srcfolder "$STAGE" -ov -format UDZO \
  "dist/Redactor-$VERSION-macos-$(uname -m).dmg"
