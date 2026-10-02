#!/usr/bin/env sh
# Create a local operator backup. Credentials are read only from the running Compose service.
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /absolute/or-relative/backup-directory" >&2
  exit 64
fi

destination=$1
timestamp=$(date +%Y%m%dT%H%M%S)
archive_dir="$destination/modai-$timestamp"

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 69; }
mkdir -p "$archive_dir"
umask 077

docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-rag_platform}" > "$archive_dir/postgres.sql"
docker compose cp qdrant:/qdrant/storage "$archive_dir/qdrant-storage"
docker compose cp worker:/data/modai "$archive_dir/modaidata"

printf '%s\n' "Backup created at $archive_dir"
printf '%s\n' "Copy the configured model/cache directory and a separately protected .env backup before treating this as a complete restore set."
