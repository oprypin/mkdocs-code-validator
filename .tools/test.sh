#!/bin/sh
set -e -x

cd "$(dirname "$0")/.."

mkdocs build -f examples/good/mkdocs.yml --strict
mkdocs --version | grep -E '\b1\.[01]\.' && exit 0 || true
mkdocs build -f examples/bad/mkdocs.yml --strict
! env LINT=true mkdocs build -f examples/bad/mkdocs.yml --strict
