#!/bin/sh
# Section 13: "daily encrypted pg_dump (14 days)". Encrypts with the same
# APP_SECRET_KEY-derived passphrase approach as the rest of the app (no
# new secret to manage) via openssl's AES-256. Retention (14 days) and
# actual scheduling (cron/systemd timer on the real host) are left to
# the deployment target — this script just does one backup correctly.
#
# Verified by this session's manual pg_dump -> pg_restore round trip
# (docs/decision-log.md, Phase 8): a real dump of the dev DB restored
# cleanly into a fresh database with all 15 tables and real row counts
# intact. This script wraps the same pg_dump call with encryption.
set -eu

: "${BACKUP_DIR:=./backups}"
: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE (e.g. derive from APP_SECRET_KEY) before running}"

mkdir -p "$BACKUP_DIR"
timestamp=$(date +%Y%m%dT%H%M%SZ)
dump_file="$BACKUP_DIR/icm-$timestamp.dump"
enc_file="$dump_file.enc"

docker exec infra-postgres-1 pg_dump -U icm_owner -d icm -F c -f "/tmp/$(basename "$dump_file")"
docker cp "infra-postgres-1:/tmp/$(basename "$dump_file")" "$dump_file"
docker exec infra-postgres-1 rm -f "/tmp/$(basename "$dump_file")"

openssl enc -aes-256-cbc -pbkdf2 -salt -pass "pass:$BACKUP_PASSPHRASE" -in "$dump_file" -out "$enc_file"
rm "$dump_file"

echo "Backup written: $enc_file"
find "$BACKUP_DIR" -name "*.dump.enc" -mtime +14 -delete
