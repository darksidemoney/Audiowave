#!/usr/bin/env bash
set -euo pipefail

echo "Testing simple separation..."

# Set environment variables to avoid SSL issues
export PYTHONHTTPSVERIFY=0
export CURL_CA_BUNDLE=""

# Run the separation
cd src/workers/separation
python3 separate.py audio.mp3 --inputs_dir ../../../audio_inputs --outputs_dir ../../../audio_outputs

echo "Done! Check: audio_outputs/audio/" 