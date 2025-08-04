#!/usr/bin/env python3
"""
Tempo and Key detection worker for Audiowave project

Extracts tempo (BPM) and key/scale information from audio files
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional
import numpy as np
import librosa
import soundfile as sf
from essentia import Pool, run
from essentia.standard import (
    EasyLoader, 
    RhythmExtractor2013, 
    KeyExtractor
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TempoKeyWorker:
    """Tempo and Key detection worker for APF project"""
    
    def __init__(self):
        """Initialize the tempo/key worker"""
        logger.info("Initializing TempoKeyWorker")
        
    def extract_tempo_librosa(self, audio_path: str) -> Tuple[float, float]:
        """
        Extract tempo using librosa's beat tracking
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Tuple of (tempo_bpm, confidence)
        """
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=None)
            
            # Extract tempo using librosa
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            
            # Calculate confidence based on beat consistency
            if len(beats) > 1:
                beat_intervals = np.diff(beats)
                mean_interval = float(np.mean(beat_intervals))
                std_interval = float(np.std(beat_intervals))
                if mean_interval > 0:
                    confidence = 1.0 - (std_interval / mean_interval)
                    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
                else:
                    confidence = 0.5
            else:
                confidence = 0.5
                
            tempo_scalar = float(tempo.item() if hasattr(tempo, 'item') else tempo)
            logger.info(f"Librosa tempo: {tempo_scalar:.1f} BPM (confidence: {confidence:.2f})")
            return tempo_scalar, confidence
            
        except Exception as e:
            logger.error(f"Librosa tempo extraction failed: {e}")
            raise
    
    def extract_tempo_essentia(self, audio_path: str) -> Tuple[float, float]:
        """
        Extract tempo using Essentia's RhythmExtractor2013
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Tuple of (tempo_bpm, confidence)
        """
        try:
            # Load audio
            loader = EasyLoader(filename=audio_path)
            audio = loader()
            
            # Extract rhythm
            rhythm_extractor = RhythmExtractor2013()
            bpm, ticks, confidence, estimates, bpmIntervals = rhythm_extractor(audio)
            
            bpm_scalar = float(bpm.item() if hasattr(bpm, 'item') else bpm)
            conf_scalar = float(confidence.item() if hasattr(confidence, 'item') else confidence)
            logger.info(f"Essentia tempo: {bpm_scalar:.1f} BPM (confidence: {conf_scalar:.2f})")
            return bpm_scalar, conf_scalar
            
        except Exception as e:
            logger.error(f"Essentia tempo extraction failed: {e}")
            raise
    
    def extract_key_essentia(self, audio_path: str) -> Tuple[str, str, float]:
        """
        Extract key using Essentia's KeyExtractor
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Tuple of (key, scale, confidence)
        """
        try:
            # Load audio
            loader = EasyLoader(filename=audio_path)
            audio = loader()
            
            # Extract key
            key_extractor = KeyExtractor()
            key, scale, strength = key_extractor(audio)
            
            strength_scalar = float(strength.item() if hasattr(strength, 'item') else strength)
            logger.info(f"Essentia key: {key} {scale} (strength: {strength_scalar:.2f})")
            return str(key), str(scale), strength_scalar
            
        except Exception as e:
            logger.error(f"Essentia key extraction failed: {e}")
            raise
    
    def extract_key_librosa(self, audio_path: str) -> Tuple[str, str, float]:
        """
        Extract key using librosa's key detection
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Tuple of (key, scale, confidence)
        """
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=None)
            
            # Extract chromagram
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            
            # Use librosa's key detection (simplified approach)
            # librosa doesn't have a built-in key detection, so we'll use a simple approach
            # based on chroma vector correlation with major/minor profiles
            
            # Define major and minor key profiles (simplified)
            major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
            minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
            
            # Normalize profiles
            major_profile = major_profile / np.sum(major_profile)
            minor_profile = minor_profile / np.sum(minor_profile)
            
            # Calculate average chroma vector
            avg_chroma = np.mean(chroma, axis=1)
            avg_chroma = avg_chroma / np.sum(avg_chroma)
            
            # Find best correlation for each key
            best_correlation = -1
            best_key = "C"
            best_scale = "major"
            
            for i in range(12):
                # Test major key
                shifted_major = np.roll(major_profile, i)
                correlation = np.corrcoef(avg_chroma, shifted_major)[0, 1]
                if correlation > best_correlation:
                    best_correlation = correlation
                    best_key = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][i]
                    best_scale = "major"
                
                # Test minor key
                shifted_minor = np.roll(minor_profile, i)
                correlation = np.corrcoef(avg_chroma, shifted_minor)[0, 1]
                if correlation > best_correlation:
                    best_correlation = correlation
                    best_key = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][i]
                    best_scale = "minor"
            
            # Convert correlation to confidence (0-1)
            confidence = max(0.0, min(1.0, (best_correlation + 1) / 2))
            
            logger.info(f"Librosa key: {best_key} {best_scale} (confidence: {confidence:.2f})")
            return best_key, best_scale, confidence
            
        except Exception as e:
            logger.error(f"Librosa key extraction failed: {e}")
            raise
    
    def analyze_audio(self, audio_path: str) -> Dict:
        """
        Analyze audio for tempo and key information
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict with tempo and key information
        """
        try:
            logger.info(f"Analyzing audio: {audio_path}")
            
            # Extract tempo using both methods
            tempo_librosa, conf_librosa = self.extract_tempo_librosa(audio_path)
            tempo_essentia, conf_essentia = self.extract_tempo_essentia(audio_path)
            
            # Choose the method with higher confidence
            if conf_essentia > conf_librosa:
                tempo_bpm = tempo_essentia
                tempo_confidence = conf_essentia
                tempo_method = "essentia"
            else:
                tempo_bpm = tempo_librosa
                tempo_confidence = conf_librosa
                tempo_method = "librosa"
            
            # Extract key using both methods
            key_essentia, scale_essentia, strength_essentia = self.extract_key_essentia(audio_path)
            key_librosa, scale_librosa, conf_librosa = self.extract_key_librosa(audio_path)
            
            # Choose the method with higher confidence
            if strength_essentia > conf_librosa:
                key = key_essentia
                scale = scale_essentia
                key_confidence = strength_essentia
                key_method = "essentia"
            else:
                key = key_librosa
                scale = scale_librosa
                key_confidence = conf_librosa
                key_method = "librosa"
            
            # Format key as key_scale
            key_scale = f"{key}_{scale}"
            
            result = {
                "tempo_bpm": round(tempo_bpm, 1),
                "tempo_confidence": round(tempo_confidence, 2),
                "tempo_method": tempo_method,
                "key_scale": key_scale,
                "key_confidence": round(key_confidence, 2),
                "key_method": key_method,
                "analysis_metadata": {
                    "librosa_tempo": round(tempo_librosa, 1),
                    "librosa_tempo_confidence": round(conf_librosa, 2),
                    "essentia_tempo": round(tempo_essentia, 1),
                    "essentia_tempo_confidence": round(conf_essentia, 2),
                    "essentia_key": f"{key_essentia}_{scale_essentia}",
                    "essentia_key_strength": round(strength_essentia, 2),
                    "librosa_key": f"{key_librosa}_{scale_librosa}",
                    "librosa_key_confidence": round(conf_librosa, 2)
                }
            }
            
            logger.info(f"Analysis complete: {tempo_bpm:.1f} BPM, {key_scale}")
            return result
            
        except Exception as e:
            logger.error(f"Audio analysis failed: {e}")
            raise
    
    def process_file(self, input_path: str, output_dir: str) -> str:
        """
        Process a single audio file and save results
        
        Args:
            input_path: Path to input audio file
            output_dir: Directory to save results
            
        Returns:
            Path to the output JSON file
        """
        try:
            # Create output directory
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Analyze the audio
            result = self.analyze_audio(input_path)
            
            # Save results
            output_path = os.path.join(output_dir, "tempo_key.json")
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)
            
            logger.info(f"Results saved to: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            raise

def main():
    """Main entry point"""
    if len(sys.argv) != 2:
        print("Usage: python tempo_key.py <audio_file>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    if not os.path.exists(audio_file):
        print(f"Error: Audio file not found: {audio_file}")
        sys.exit(1)
    
    # Determine output directory based on input filename
    input_name = Path(audio_file).stem
    output_dir = f"audio_outputs/{input_name}"
    
    # Process the file
    worker = TempoKeyWorker()
    try:
        output_path = worker.process_file(audio_file, output_dir)
        print(f"✅ Tempo/Key analysis complete: {output_path}")
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 