#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docs/deployment/docker/docker-compose.yml"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <original-audio-file-path or basename>"
  echo "Example: $0 ~/Downloads/test.mp3"
  exit 1
fi

ARG="$1"
BASENAME="$(basename "$ARG")"
CLIP="${BASENAME%.*}"

# Build and run tagger against the clip folder created by separation
docker compose -f "$COMPOSE_FILE" build tagger
docker compose -f "$COMPOSE_FILE" run --rm tagger "$CLIP"

echo "Done. See: audio_outputs/$CLIP/tags.json" 