#!/usr/bin/env bash
set -euo pipefail

echo "Testing separation from project root..."

# Run from project root with correct paths
cd src/workers/separation
python3 separate.py audio.mp3 --inputs_dir ../../../audio_inputs --outputs_dir ../../../audio_outputs

echo "Done! Check: audio_outputs/audio/" 