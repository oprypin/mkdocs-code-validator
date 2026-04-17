#!/bin/sh
set -e -x

cd "$(dirname "$0")/.."

properdocs build -f examples/good/properdocs.yml --strict
properdocs --version | grep -E '\b1\.[01]\.' && exit 0 || true
properdocs build -f examples/bad/properdocs.yml --strict
! env LINT=true properdocs build -f examples/bad/properdocs.yml --strict
