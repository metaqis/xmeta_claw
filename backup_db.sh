#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_FILE="$ROOT_DIR/backend/.env"

OUT_DIR="$ROOT_DIR/backups"
FORMAT="c"
SCHEMA_ONLY="0"
ENV_FILE="$DEFAULT_ENV_FILE"
export ENV_FILE

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --format)
      FORMAT="$2"
      shift 2
      ;;
    --schema-only)
      SCHEMA_ONLY="1"
      shift 1
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [--out-dir DIR] [--format c|p|t] [--schema-only] [--env-file PATH]"
      echo "Defaults:"
      echo "  --out-dir   $OUT_DIR"
      echo "  --format    $FORMAT"
      echo "  --env-file  $ENV_FILE"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${DATABASE_URL_SYNC:-}" ]]; then
  if [[ -f "$ENV_FILE" ]]; then
    DATABASE_URL_SYNC="$(python3 - <<PY
import os, re, sys
path = os.environ.get("ENV_FILE")
data = open(path, "r", encoding="utf-8").read().splitlines()
for line in data:
  m = re.match(r"^DATABASE_URL_SYNC=(.*)$", line.strip())
  if m:
    print(m.group(1))
    sys.exit(0)
sys.exit(1)
PY
)"
  else
    echo "DATABASE_URL_SYNC is not set and env file not found: $ENV_FILE" >&2
    exit 1
  fi
fi
export DATABASE_URL_SYNC

PARSED="$(python3 - <<'PY'
import os, sys
from urllib.parse import urlparse

u = urlparse(os.environ["DATABASE_URL_SYNC"])
if u.scheme not in ("postgresql", "postgres"):
  raise SystemExit("DATABASE_URL_SYNC must be postgresql://...")

user = u.username or "postgres"
password = u.password or ""
host = u.hostname or "localhost"
port = str(u.port or 5432)
dbname = (u.path or "").lstrip("/") or "postgres"

print("\n".join([user, password, host, port, dbname]))
PY
)"

DB_USER="$(echo "$PARSED" | sed -n '1p')"
DB_PASS="$(echo "$PARSED" | sed -n '2p')"
DB_HOST="$(echo "$PARSED" | sed -n '3p')"
DB_PORT="$(echo "$PARSED" | sed -n '4p')"
DB_NAME="$(echo "$PARSED" | sed -n '5p')"

mkdir -p "$OUT_DIR"
TS="$(date +"%Y%m%d_%H%M%S")"
EXT="dump"
if [[ "$FORMAT" == "p" ]]; then EXT="sql"; fi
if [[ "$FORMAT" == "t" ]]; then EXT="tar"; fi
OUT_FILE="$OUT_DIR/${DB_NAME}_${TS}.${EXT}"

PGPASSFILE_TMP=""
if [[ -n "$DB_PASS" ]]; then
  PGPASSFILE_TMP="$(mktemp)"
  chmod 600 "$PGPASSFILE_TMP"
  printf "%s:%s:%s:%s:%s\n" "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASS" > "$PGPASSFILE_TMP"
  export PGPASSFILE="$PGPASSFILE_TMP"
fi

ARGS=(--host "$DB_HOST" --port "$DB_PORT" --username "$DB_USER" --format "$FORMAT" --file "$OUT_FILE")
if [[ "$SCHEMA_ONLY" == "1" ]]; then
  ARGS+=(--schema-only)
fi

pg_dump "${ARGS[@]}" "$DB_NAME"

if [[ -n "$PGPASSFILE_TMP" ]]; then
  rm -f "$PGPASSFILE_TMP"
  unset PGPASSFILE
fi

echo "$OUT_FILE"
