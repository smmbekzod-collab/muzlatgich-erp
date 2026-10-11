#!/usr/bin/env bash
set -Eeuo pipefail

# The ONLY source this tool may read is the preapproved isolated STAGING DB.
# No write queries are sent to SOURCE_DATABASE_URL.
EXPECTED_ENV="79dae0a2-be02-4dc2-ac16-3675ffc1aa62"
if [[ "${RAILWAY_ENVIRONMENT_ID:-}" != "$EXPECTED_ENV" ]]; then
  echo "REFUSED: this drill is only permitted in the isolated STAGING environment."
  exit 45
fi
if [[ -z "${SOURCE_DATABASE_URL:-}" ]]; then
  echo "REFUSED: SOURCE_DATABASE_URL is required."
  exit 46
fi

backup_dir=$(mktemp -d)
chmod 700 "$backup_dir"
chown postgres:postgres "$backup_dir"
started=0
cleanup() {
  if [[ "$started" == 1 ]]; then
    runuser -u postgres -- pg_ctl -D "$backup_dir/cluster" -m immediate -w stop >/dev/null 2>&1 || true
  fi
  rm -rf "$backup_dir"
  echo "TEMP_BACKUP_REMOVED"
}
trap cleanup EXIT

echo "RESTORE_DRILL_START: staging dump to temporary local file only."
pg_dump --dbname="$SOURCE_DATABASE_URL" --format=custom --no-owner --no-acl --file="$backup_dir/snapshot.dump"
test -s "$backup_dir/snapshot.dump"
pg_restore --list "$backup_dir/snapshot.dump" > /dev/null
echo "DUMP_OK bytes=$(wc -c < "$backup_dir/snapshot.dump")"

# Temporary local PostgreSQL cluster inside THIS helper container only.
# No network service/domain/public proxy, no attachment to the source database.
runuser -u postgres -- initdb -D "$backup_dir/cluster" -A trust >/dev/null
runuser -u postgres -- pg_ctl -D "$backup_dir/cluster" -o "-k $backup_dir -p 55432 -c listen_addresses=''" -l "$backup_dir/postgres.log" -w start >/dev/null
started=1
runuser -u postgres -- createdb -h "$backup_dir" -p 55432 -U postgres restored_test
pg_restore --exit-on-error --no-owner --no-acl -h "$backup_dir" -p 55432 -U postgres -d restored_test "$backup_dir/snapshot.dump"
echo "RESTORE_OK: isolated database created"

# Read-only check against source; restored copy must reproduce key row counts.
for table in core_organization warehouse_lot warehouse_operation warehouse_camerarentalinvoice warehouse_camerarentalpayment warehouse_dailytelegramdigest; do
  source_count=$(psql "$SOURCE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM $table")
  restored_count=$(psql -h "$backup_dir" -p 55432 -U postgres -d restored_test -X -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM $table")
  echo "TABLE_MATCH $table source=$source_count restored=$restored_count"
  if [[ "$source_count" != "$restored_count" ]]; then
    echo "RESTORE_VALIDATION_FAILED"
    exit 47
  fi
done
echo "RESTORE_DRILL_OK: staging snapshot restored and six critical table counts matched"
