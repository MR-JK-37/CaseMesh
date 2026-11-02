#!/bin/sh
# Counterpart to backup.sh: decrypts and restores into a NEW database
# (never overwrites the live one directly) so a bad restore is cheap to
# throw away. Usage: ./restore.sh <path-to.dump.enc> <target_db_name>
set -eu

: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE to the same value used for backup.sh}"

enc_file="${1:?Usage: restore.sh <backup.dump.enc> <target_db_name>}"
target_db="${2:?Usage: restore.sh <backup.dump.enc> <target_db_name>}"
dump_file=$(mktemp)

openssl enc -d -aes-256-cbc -pbkdf2 -salt -pass "pass:$BACKUP_PASSPHRASE" -in "$enc_file" -out "$dump_file"

docker exec infra-postgres-1 psql -U icm_owner -d icm -c "CREATE DATABASE $target_db OWNER icm_owner;"
docker cp "$dump_file" "infra-postgres-1:/tmp/restore.dump"
docker exec infra-postgres-1 pg_restore -U icm_owner -d "$target_db" --no-owner /tmp/restore.dump
docker exec infra-postgres-1 rm -f /tmp/restore.dump
rm "$dump_file"

echo "Restored into database: $target_db (verify, then drop it or promote it manually)"
