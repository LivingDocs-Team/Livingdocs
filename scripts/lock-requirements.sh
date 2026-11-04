#!/usr/bin/env bash
# Regenerate fully pinned requirements.txt (direct + transitive) for the Python
# services from their requirements.in. Needs `uv` and access to PyPI.
# Existing pins in requirements.txt are kept as preferences; add --upgrade to
# uv to move to the newest allowed versions instead.
# Targets Python 3.12 (the version used by the Dockerfiles and CI).
# code-analyzer is compiled first and used as a constraint for ai-service so that
# shared packages (fastapi, pydantic, uvicorn, ...) get the same version in both.
set -euo pipefail
cd "$(dirname "$0")/.."

opts=(--python-version 3.12 --annotation-style line)

uv pip compile code-analyzer/requirements.in -o code-analyzer/requirements.txt "${opts[@]}"
uv pip compile ai-service/requirements.in -c code-analyzer/requirements.txt \
  -o ai-service/requirements.txt "${opts[@]}"

echo "Done. Review the diff, then commit requirements.in and requirements.txt together."
