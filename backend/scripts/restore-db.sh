#!/usr/bin/env bash
#
# Restore Supabase DB from a snapshot stored in AliCloud OSS.
#
# Usage:
#   ./backend/scripts/restore-db.sh <YYYY-MM-DD> [path/to/.env]
#
# By default loads env vars from backend/.env.bak (relative to this script).
# Pass a different file as the second arg to override.
#
# Required env vars (from .env.bak or the shell):
#   SUPABASE_SESSION_POOLER_DB_URL   Restore-target Supabase Session pooler URL, port 5432
#                                    (add to .env.bak manually — distinct from the app's SUPABASE_URL)
#   ALICLOUD_ACCESS_KEY_ID
#   ALICLOUD_ACCESS_KEY_SECRET
#   ALICLOUD_OSS_ENDPOINT
#   ALICLOUD_OSS_BUCKET
#
# What it does:
#   1. Downloads roles/schema/data .sql.gz from oss://$ALICLOUD_OSS_BUCKET/db-backups/<date>/
#   2. Decompresses them in a temp dir (auto-cleaned)
#   3. Asks for confirmation, then DROPs and recreates the public schema on SUPABASE_SESSION_POOLER_DB_URL
#   4. Loads roles -> schema -> data in order
#   5. Prints row counts for a couple of key tables as a sanity check
#
# Notes:
#   - SUPABASE_SESSION_POOLER_DB_URL must use the Session pooler (port 5432). Direct connection is IPv6-only on free tier.
#   - Roles errors ("role X already exists") are tolerated — Supabase pre-creates anon/authenticated/service_role.
#   - Schema and data steps abort on first error (ON_ERROR_STOP=1). A half-restored state is worse than a failed one.
#   - Built-in schemas (auth, storage, realtime, extensions) are NOT touched.
#   - auth.users data is NOT in the backup; users have to be reinvited or restored via Supabase Admin API.

set -euo pipefail

DATE="${1:-}"
if [[ -z "$DATE" ]]; then
  echo "Usage: $0 <YYYY-MM-DD> [path/to/.env]" >&2
  echo "       (the date corresponds to a folder under oss://\$ALICLOUD_OSS_BUCKET/db-backups/)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${2:-$SCRIPT_DIR/../.env.bak}"

if [[ -f "$ENV_FILE" ]]; then
  echo "Loading env from: $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Env file not found: $ENV_FILE (continuing with shell env only)" >&2
fi

: "${SUPABASE_SESSION_POOLER_DB_URL:?Set SUPABASE_SESSION_POOLER_DB_URL (Supabase Session pooler URL, port 5432) — add it to $ENV_FILE or export it}"
: "${ALICLOUD_ACCESS_KEY_ID:?Missing ALICLOUD_ACCESS_KEY_ID}"
: "${ALICLOUD_ACCESS_KEY_SECRET:?Missing ALICLOUD_ACCESS_KEY_SECRET}"
: "${ALICLOUD_OSS_ENDPOINT:?Missing ALICLOUD_OSS_ENDPOINT}"
: "${ALICLOUD_OSS_BUCKET:?Missing ALICLOUD_OSS_BUCKET}"

command -v aliyun >/dev/null 2>&1 || {
  echo "aliyun CLI not found. Install: brew install aliyun-cli" >&2
  exit 1
}
command -v psql    >/dev/null 2>&1 || {
  echo "psql not found. Install postgresql-client (brew install libpq && brew link --force libpq)." >&2
  exit 1
}

WORKDIR="$(mktemp -d -t restore-${DATE}-XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT
echo "Workdir: $WORKDIR"

# --- 1. Download from OSS ---
echo
echo "==> Downloading snapshot $DATE from oss://${ALICLOUD_OSS_BUCKET}/db-backups/${DATE}/"
aliyun oss cp "oss://${ALICLOUD_OSS_BUCKET}/db-backups/${DATE}/" "$WORKDIR/" \
  --mode AK \
  --access-key-id "$ALICLOUD_ACCESS_KEY_ID" \
  --access-key-secret "$ALICLOUD_ACCESS_KEY_SECRET" \
  --endpoint "$ALICLOUD_OSS_ENDPOINT" \
  --recursive \
  --force

# --- 2. Decompress ---
echo
echo "==> Decompressing"
gunzip "$WORKDIR"/*.sql.gz
ls -lh "$WORKDIR"

for f in roles.sql schema.sql data.sql; do
  [[ -f "$WORKDIR/$f" ]] || { echo "Missing $f in snapshot" >&2; exit 1; }
done

# --- 3. Confirm before destructive op ---
TARGET_HOST="$(printf '%s' "$SUPABASE_SESSION_POOLER_DB_URL" | sed -E 's|.*@([^:/]+).*|\1|')"
echo
echo "About to DROP and recreate the 'public' schema on:"
echo "  host: $TARGET_HOST"
echo "  snapshot: $DATE"
echo
read -r -p "Type 'yes' to continue: " confirm
[[ "$confirm" == "yes" ]] || { echo "Aborted." >&2; exit 1; }

# --- 4. Wipe public schema ---
echo
echo "==> Wiping public schema"
psql "$SUPABASE_SESSION_POOLER_DB_URL" -v ON_ERROR_STOP=1 <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
SQL

# --- 5. Restore in order ---
echo
echo "==> Restoring roles (errors here are usually harmless)"
psql "$SUPABASE_SESSION_POOLER_DB_URL" -f "$WORKDIR/roles.sql" || \
  echo "(roles step had errors; continuing — Supabase pre-creates the standard roles)"

echo
echo "==> Restoring schema"
psql "$SUPABASE_SESSION_POOLER_DB_URL" -v ON_ERROR_STOP=1 -f "$WORKDIR/schema.sql"

echo
echo "==> Restoring data"
psql "$SUPABASE_SESSION_POOLER_DB_URL" -v ON_ERROR_STOP=1 -f "$WORKDIR/data.sql"

# --- 6. Sanity check ---
echo
echo "==> Sanity check"
psql "$SUPABASE_SESSION_POOLER_DB_URL" -c "
  SELECT 'meetings'  AS table, count(*) FROM meetings
  UNION ALL SELECT 'attendees', count(*) FROM attendees
  UNION ALL SELECT 'awards',    count(*) FROM awards
  UNION ALL SELECT 'votes',     count(*) FROM votes;
"

echo
echo "Done. Don't forget to:"
echo "  - point backend env vars at the new project (Supabase URL + service role key + JWT secret)"
echo "  - point frontend NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY at the new project"
echo "  - re-invite users (auth.users is not in the backup)"
