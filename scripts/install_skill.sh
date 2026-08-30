#!/usr/bin/env bash
set -euo pipefail

TARGET="skills/asd-ste100"

rm -rf "$TARGET"
git clone https://github.com/danyuchn/asd-ste100-skill "$TARGET"

echo "Installed ASD-STE100 skill into $TARGET"
