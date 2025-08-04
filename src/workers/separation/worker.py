#!/usr/bin/env python3
"""
HT-Demucs separation worker for Audiowave project

Handles source separation for the Audiowave project
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
import torch
import torchaudio
from demucs.api import Separator
from demucs.pretrained import get_model
import soundfile as sf
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DemucsWorker:
    """HT-Demucs separation worker for APF project"""
    
    def __init__(self, model_name: str = "htdemucs"):
        """Initialize the separation worker"""
        self.model_name = model_name
        self.separator = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Initializing DemucsWorker with model: {model_name}")
        logger.info(f"Using device: {self.device}")
        
    def load_model(self):
        """Load the HT-Demucs model"""
        try:
            # Initialize separator with HT-Demucs model
            self.separator = Separator(
                model=self.model_name,
                device=self.device,
                shifts=1,  # No shifts for faster processing
                split=True,  # Split long audio
                overlap=0.25,  # 25% overlap
                progress=True
            )
            logger.info(f"Successfully loaded {self.model_name} model")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def separate_audio(self, input_path: str, output_dir: str) -> Dict[str, str]:
        """
        Separate audio into stems
        
        Args:
            input_path: Path to input audio file
            output_dir: Directory to save separated stems
            
        Returns:
            Dict mapping stem names to file paths
        """
        if self.separator is None:
            self.load_model()
        
        try:
            # Create output directory
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Perform separation
            logger.info(f"Separating audio: {input_path}")
            sources = self.separator.separate_file(input_path)
            
            # Save separated stems
            stem_paths = {}
            for stem_name, audio in sources.items():
                output_path = os.path.join(output_dir, f"{stem_name}.wav")
                
                # Convert to numpy and save
                if isinstance(audio, torch.Tensor):
                    audio_np = audio.cpu().numpy()
                else:
                    audio_np = audio
                
                # Ensure audio is 2D (channels, samples)
                if audio_np.ndim == 1:
                    audio_np = audio_np[np.newaxis, :]
                
                sf.write(output_path, audio_np.T, self.separator.samplerate)
                stem_paths[stem_name] = output_path
                logger.info(f"Saved {stem_name} to {output_path}")
            
            return stem_paths
            
        except Exception as e:
            logger.error(f"Separation failed: {e}")
            raise
    
    def get_stem_info(self, stem_paths: Dict[str, str]) -> Dict[str, Dict]:
        """
        Get information about separated stems
        
        Args:
            stem_paths: Dict of stem names to file paths
            
        Returns:
            Dict with stem information (duration, sample rate, etc.)
        """
        stem_info = {}
        
        for stem_name, path in stem_paths.items():
            try:
                # Load audio to get metadata
                audio, sample_rate = sf.read(path)
                
                # Calculate duration
                duration = len(audio) / sample_rate
                
                # Calculate RMS (loudness)
                rms = np.sqrt(np.mean(audio**2))
                
                stem_info[stem_name] = {
                    "path": path,
                    "duration": duration,
                    "sample_rate": sample_rate,
                    "channels": audio.shape[1] if audio.ndim > 1 else 1,
                    "rms": float(rms),
                    "file_size": os.path.getsize(path)
                }
                
            except Exception as e:
                logger.error(f"Failed to get info for {stem_name}: {e}")
                stem_info[stem_name] = {"error": str(e)}
        
        return stem_info

def main():
    """Main worker function"""
    # Get environment variables
    model_name = os.getenv("DEMUCS_MODEL", "htdemucs")
    input_dir = os.getenv("AUDIO_INPUTS_DIR", "/app/audio_inputs")
    output_dir = os.getenv("AUDIO_OUTPUTS_DIR", "/app/audio_outputs")
    
    # Initialize worker
    worker = DemucsWorker(model_name=model_name)
    
    # Load model
    worker.load_model()
    
    # Process audio files in input directory
    input_path = Path(input_dir)
    if input_path.exists():
        for audio_file in input_path.glob("*.wav"):
            logger.info(f"Processing {audio_file}")
            
            # Create output subdirectory for this file
            file_output_dir = Path(output_dir) / audio_file.stem
            file_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Separate audio
            stem_paths = worker.separate_audio(
                str(audio_file), 
                str(file_output_dir)
            )
            
            # Get stem information
            stem_info = worker.get_stem_info(stem_paths)
            
            # Log results
            logger.info(f"Separation complete for {audio_file}")
            for stem_name, info in stem_info.items():
                if "error" not in info:
                    logger.info(f"  {stem_name}: {info['duration']:.2f}s, {info['rms']:.4f} RMS")
    
    logger.info("Worker ready for processing")

if __name__ == "__main__":
    main() 