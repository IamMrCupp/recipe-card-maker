#!/bin/sh
# Home-base entrypoint (Phase 4α): seed the DB from the baked-in markdown corpus
# on first boot only, then serve. Subsequent boots never touch existing data —
# the DB on the volume is the source of truth.
set -e

db_path="${RCM_DB_PATH:-/data/recipes.db}"
media_dir="${RCM_MEDIA_DIR:-/data/media}"

mkdir -p "$(dirname "$db_path")" "$media_dir"

if [ ! -f "$db_path" ]; then
    echo "==> No database at $db_path — seeding from the committed corpus"
    python -m _app.corpus import
fi

exec python -m uvicorn _app.main:app --host 0.0.0.0 --port 8000
