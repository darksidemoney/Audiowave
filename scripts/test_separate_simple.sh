#!/usr/bin/env bash
set -euo pipefail

echo "Testing separation with direct file path..."

# Go to the separation directory
cd src/workers/separation

# Run with the full path to the audio file
python3 separate.py ../../audio_inputs/audio.mp3 --inputs_dir ../../audio_inputs --outputs_dir ../../audio_outputs

echo "Done! Check: ../../audio_outputs/audio/" 