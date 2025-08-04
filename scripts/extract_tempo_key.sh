#!/bin/bash

# Test script for tempo_key worker
# Usage: ./scripts/extract_tempo_key.sh <audio_file>

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <audio_file>"
    echo "Example: $0 audio_inputs/audio.mp3"
    exit 1
fi

AUDIO_FILE="$1"
FILENAME=$(basename "$AUDIO_FILE")
NAME_WITHOUT_EXT="${FILENAME%.*}"

echo "🎵 Testing Tempo/Key extraction..."
echo "Input: $AUDIO_FILE"

# Check if file exists
if [ ! -f "$AUDIO_FILE" ]; then
    echo "❌ Error: Audio file not found: $AUDIO_FILE"
    exit 1
fi

# Build the tempo_key container
echo "🔨 Building tempo_key container..."
cd src/workers/tempo_key
docker build -t tempo_key:latest .

# Run the analysis
echo "🚀 Running tempo/key analysis..."
docker run --rm \
    -v "$(pwd)/../../../audio_inputs:/app/audio_inputs" \
    -v "$(pwd)/../../../audio_outputs:/app/audio_outputs" \
    tempo_key:latest \
    "/app/audio_inputs/$FILENAME"

# Check results
OUTPUT_DIR="../../../audio_outputs/$NAME_WITHOUT_EXT"
OUTPUT_FILE="$OUTPUT_DIR/tempo_key.json"

if [ -f "$OUTPUT_FILE" ]; then
    echo "✅ Tempo/Key analysis complete!"
    echo "📄 Results: $OUTPUT_FILE"
    echo ""
    echo "📊 Analysis results:"
    cat "$OUTPUT_FILE" | python3 -m json.tool
else
    echo "❌ Error: Output file not found: $OUTPUT_FILE"
    exit 1
fi

echo ""
echo "🎯 Next steps:"
echo "  - Review tempo accuracy (±1 BPM target)"
echo "  - Review key accuracy (correct/relative target)"
echo "  - Check runtime (< 2s on 30s clip)" 