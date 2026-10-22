#!/usr/bin/env sh
set -e

# Apply database migrations on every (re)deploy. The schema is owned by Alembic
# in all containerised environments; SQLite (local test suite) skips this and
# relies on create_all instead.
if [ -n "${DATABASE_URL}" ] && echo "${DATABASE_URL}" | grep -q "sqlite"; then
  echo "SQLite database detected; skipping Alembic migrations (using create_all)."
else
  echo "Applying database migrations (alembic upgrade head)..."
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8010
