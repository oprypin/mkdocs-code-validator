#!/bin/sh
set -e

cd "$(dirname "$0")/.."

mkdocs build -f examples/good/mkdocs.yml -q --strict
mkdocs --version | grep -E '\b1\.[01]\.' && exit 0 || true
mkdocs build -f examples/bad/mkdocs.yml -q --strict
! env LINT=true mkdocs build -f examples/bad/mkdocs.yml -q --strict >/dev/null 2>/dev/null
