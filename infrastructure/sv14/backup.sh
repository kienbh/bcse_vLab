#!/usr/bin/env bash
# Daily pg_dump cron — to be installed via crontab on SV14.
# Install: sudo crontab -e
#   0 3 * * *  /opt/vju-lab-portal/infrastructure/sv14/backup.sh >> /var/log/labportal-backup.log 2>&1
set -euo pipefail

DEST=/opt/vju-lab-portal/postgres-backup
RETENTION_DAYS=30
TS=$(date -u +%Y%m%dT%H%M%SZ)

mkdir -p "$DEST"

# Read POSTGRES_USER / POSTGRES_DB from container env (so we don't hardcode credentials).
PG_USER=$(docker inspect --format='{{range .Config.Env}}{{println .}}{{end}}' vju-lab-portal-postgres-1 \
    | awk -F= '/^POSTGRES_USER=/ {print $2}')
PG_DB=$(docker inspect --format='{{range .Config.Env}}{{println .}}{{end}}' vju-lab-portal-postgres-1 \
    | awk -F= '/^POSTGRES_DB=/ {print $2}')

# App DB — primary. Custom format so pg_restore can selectively recover.
docker exec vju-lab-portal-postgres-1 pg_dump -U "$PG_USER" -d "$PG_DB" --format=custom \
    > "$DEST/labportal-$TS.dump"
gzip --best "$DEST/labportal-$TS.dump"

# Retention: 30 days
find "$DEST" -name 'labportal-*.dump.gz' -mtime +$RETENTION_DAYS -delete

# Log + size summary
SZ_LAB=$(stat -c '%s' "$DEST/labportal-$TS.dump.gz")
echo "[backup] $TS — labportal=$SZ_LAB B"
