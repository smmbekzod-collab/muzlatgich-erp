#!/bin/sh
# One-time STAGING ONLY PostgreSQL 18 pg_dump -> separate throwaway database.
# Never uploads or retains backups; never touches any production database.
set -eu
umask 077
expected="79dae0a2-be02-4dc2-ac16-3675ffc1aa62"
if [ "${RAILWAY_ENVIRONMENT_ID:-}" != "$expected" ] || [ "${ALLOW_RESTORE_DRILL:-}" != "yes" ]; then
    echo "REFUSED: exact ERP v2 STAGING only." >&2
    exit 91
fi
if [ -z "${DATABASE_URL:-}" ]; then
    echo "REFUSED: no isolated staging database URL." >&2
    exit 91
fi
case "$DATABASE_URL" in
    postgresql://*/railway|postgres://*/railway) : ;;
    *) echo "REFUSED: unexpected source DB URL suffix." >&2; exit 91 ;;
esac
source_name="$(psql "$DATABASE_URL" -X -qAt -v ON_ERROR_STOP=1 -c 'SELECT current_database()')"
if [ "$source_name" != "railway" ]; then
    echo "REFUSED: source database is not the expected staging DB." >&2
    exit 91
fi
temp_db="erp_restore_v2_$(date -u +%y%m%d%H%M%S)_$$"
temp_url="${DATABASE_URL%/railway}/$temp_db"
dump_file="/tmp/erp_staging_$temp_db.dump"
created=0
cleanup() {
    rm -f "$dump_file"
    if [ "$created" = "1" ]; then
        case "$temp_db" in erp_restore_v2_*) : ;; *) echo "REFUSED unsafe cleanup" >&2; return 1 ;; esac
        if dropdb --if-exists --maintenance-db="$DATABASE_URL" "$temp_db"; then
            echo "CLEANUP OK: isolated restored DB dropped."
        else
            echo "CLEANUP ERROR: inspect isolated DB $temp_db manually." >&2
            return 1
        fi
    fi
}
trap cleanup EXIT
exists="$(psql "$DATABASE_URL" -X -qAt -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM pg_database WHERE datname='$temp_db'")"
if [ "$exists" != "0" ]; then
    echo "REFUSED: temporary database name already in use." >&2
    exit 92
fi
echo "STAGING BACKUP START: consistent pg_dump snapshot (not retained)"
pg_dump "$DATABASE_URL" --format=custom --no-owner --no-acl --file="$dump_file"
test -s "$dump_file"
pg_restore --list "$dump_file" >/dev/null
dump_bytes="$(wc -c < "$dump_file" | tr -d ' ')"
echo "DUMP OK: validated custom format; bytes=$dump_bytes"
createdb --maintenance-db="$DATABASE_URL" --template=template0 "$temp_db"
created=1
echo "RESTORE START: independent PostgreSQL database $temp_db"
pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error --dbname="$temp_url" "$dump_file"

sql="SELECT CONCAT_WS('|',
    (SELECT COUNT(*) FROM django_migrations),
    (SELECT COUNT(*) FROM core_organization),
    (SELECT COUNT(*) FROM warehouse_lot),
    (SELECT COUNT(*) FROM warehouse_operation),
    (SELECT COUNT(*) FROM warehouse_camerarentalinvoice),
    (SELECT COUNT(*) FROM warehouse_camerarentalpayment),
    (SELECT COALESCE(SUM(boxes),0) FROM warehouse_lot WHERE closed_on IS NULL),
    (SELECT COALESCE(SUM(gross-tare),0) FROM warehouse_lot WHERE closed_on IS NULL),
    (SELECT COALESCE(SUM(charge),0) FROM warehouse_operation),
    (SELECT COALESCE(SUM(payment),0) FROM warehouse_operation),
    (SELECT COALESCE(SUM(amount),0) FROM warehouse_camerarentalinvoice),
    (SELECT COALESCE(SUM(amount),0) FROM warehouse_camerarentalpayment));"
source_counts="$(psql "$DATABASE_URL" -X -qAt -v ON_ERROR_STOP=1 -c "$sql")"
target_counts="$(psql "$temp_url" -X -qAt -v ON_ERROR_STOP=1 -c "$sql")"
echo "SOURCE COUNTS: $source_counts"
echo "RESTORED COUNTS: $target_counts"
if [ "$source_counts" != "$target_counts" ]; then
    echo "FAILED: source/restored financial and inventory counts differ." >&2
    exit 94
fi
lot_count="$(psql "$temp_url" -X -qAt -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM warehouse_lot l JOIN core_organization o ON o.id=l.organization_id WHERE o.code='test-agrostar-holadelnik'")"
if [ "$lot_count" -lt 6 ]; then
    echo "FAILED: expected TEST lot rows missing on restored DB." >&2
    exit 95
fi
echo "RESTORE VALIDATION OK: TEST lot rows=$lot_count; all aggregate fingerprints equal."
echo "STAGING BACKUP/RESTORE PASS: no original staging business rows altered."
