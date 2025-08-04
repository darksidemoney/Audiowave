#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <audio_file>"
  echo "Example: $0 audio_inputs/audio.mp3"
  exit 1
fi

INPUT="$1"
BASENAME="$(basename "$INPUT")"
CLIP_NAME="${BASENAME%.*}"

echo "Testing separation locally..."
echo "Input: $INPUT"
echo "Output will be in: audio_outputs/$CLIP_NAME/"

# Run separation locally with absolute paths
cd src/workers/separation
python3 separate.py "$BASENAME" --inputs_dir "$(pwd)/../../audio_inputs" --outputs_dir "$(pwd)/../../audio_outputs"

echo "Done! Check: audio_outputs/$CLIP_NAME/" 