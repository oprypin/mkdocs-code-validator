#!/bin/sh
set -e

cd "$(dirname "$0")/.."

with_groups() {
    echo "::group::$@"
    "$@" && echo "::endgroup::"
}

"$@" autoflake -i -r --remove-all-unused-imports --remove-unused-variables mkdocs_code_validator
"$@" isort -q mkdocs_code_validator
"$@" black -q mkdocs_code_validator
python -c 'import sys, os; sys.exit((3,8) <= sys.version_info < (3,10) and os.name == "posix")' ||
"$@" pytype mkdocs_code_validator

"$@" mkdocs build -f examples/good/mkdocs.yml -q --strict
mkdocs --version | grep -E '\b1\.[01]\.' && exit 0 || true
"$@" mkdocs build -f examples/bad/mkdocs.yml -q --strict
! "$@" env LINT=true mkdocs build -f examples/bad/mkdocs.yml -q --strict
