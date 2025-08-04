# Audiowave Docker Deployment

This directory contains Docker configuration for deploying Audiowave workers.

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- At least 8GB RAM available for GPU operations
- NVIDIA GPU with CUDA support (recommended)

### Running the Demucs Worker

1. **Build and start the service:**
   ```bash
   cd docs/deployment/docker
   docker-compose up --build
   ```

2. **Place audio files for processing:**
   ```bash
   # Copy your audio files to the audio_inputs directory
   cp /path/to/your/audio.wav ../../audio_inputs/
   ```

3. **Check the outputs:**
   ```bash
   # Separated stems will be in audio_outputs/
   ls ../../audio_outputs/
   ```

## Service Configuration

### Demucs Service
- **Model**: HT-Demucs (default)
- **Input**: `./audio_inputs/` directory
- **Output**: `./audio_outputs/` directory
- **Environment**: `DEMUCS_MODEL=htdemucs`

### Volume Mappings
- `./audio_inputs:/app/audio_inputs` - Input audio files
- `./audio_outputs:/app/audio_outputs` - Separated stems

## Development

### Building Locally
```bash
# Build the image
docker build -t audiowave-demucs src/workers/separation/

# Run the container
docker run --rm -v $(pwd)/audio_inputs:/app/audio_inputs -v $(pwd)/audio_outputs:/app/audio_outputs audiowave-demucs
```

### Testing
```bash
# Test with a sample audio file
docker-compose run --rm demucs python worker.py
```

## Production Deployment

### GPU Support
For production use with GPU acceleration:

```yaml
# Add to docker-compose.yml
services:
  demucs:
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
```

### Resource Limits
```yaml
# Add to docker-compose.yml
services:
  demucs:
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4'
```

## Troubleshooting

### Common Issues

1. **Out of Memory**
   - Reduce batch size in worker.py
   - Increase Docker memory limit
   - Use CPU-only mode

2. **Model Download Issues**
   - Check internet connection
   - Clear Docker cache: `docker system prune`

3. **Audio Format Issues**
   - Ensure input files are WAV format
   - Check file permissions
   - Verify audio file integrity

### Logs
```bash
# View service logs
docker-compose logs demucs

# Follow logs in real-time
docker-compose logs -f demucs
```

## Integration with Audiowave Pipeline

The Demucs worker is designed to integrate with the full Audiowave pipeline:

*For more information, see the main [Audiowave documentation](../../README.md)* 