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
python -c 'import sys, os; sys.exit((3,8) <= sys.version_info < (3,9) and os.name == "posix")' ||
"$@" pytype mkdocs_code_validator
