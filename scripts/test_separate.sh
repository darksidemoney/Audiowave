#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docs/deployment/docker/docker-compose.yml"

if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/audio.(wav|mp3)"
  exit 1
fi

INPUT="$1"
BASENAME="$(basename "$INPUT")"

# Ensure root-level canonical dirs exist
mkdir -p audio_inputs audio_outputs

# Copy test file into canonical input dir
cp "$INPUT" "audio_inputs/$BASENAME"

# Build and run
docker compose -f "$COMPOSE_FILE" build demucs
docker compose -f "$COMPOSE_FILE" run --rm demucs "audio_inputs/$BASENAME"

echo "Done. Check: audio_outputs/${BASENAME%.*}/" 