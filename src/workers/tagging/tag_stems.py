import os, json, argparse
from pathlib import Path
import numpy as np
import soundfile as sf
import librosa
from scipy.signal import periodogram
from panns_inference import AudioTagging, labels
from label_map import AUDIOSET_TO_COARSE, COARSE_TAGS, refine_synth_family, calibrate_confidence, STOP_LABELS, DRUM_LABELS, INSTRUMENT_LABELS

AUDIO_OUTPUTS = "/app/audio_outputs"
DEFAULT_TOPK = 8
MIN_SCORE = 0.18  # keep conservative to reduce garbage
TOP_K_TAGS = 3  # Allow up to 3 tags per stem
CONTENT_MIN_SCORE = 0.15  # Lower threshold to catch organ and other instruments
DEBUG = False  # Disable debug output for production

def load_audio_mono(path, sr=32000):
    y, _ = librosa.load(path, sr=sr, mono=True)
    # normalize to -1..1
    if np.max(np.abs(y)) > 0:
        y = y / np.max(np.abs(y))
    return y, sr

def detect_sidechain_pump(y, sr):
    """
    Simple periodic envelope detector:
    - compute RMS envelope
    - highpass (remove DC)
    - look for strong peak in 0.5–4 Hz (30–240 BPM quarter-note) in power spectrum
    """
    if len(y) < sr:  # too short
        return False, 0.0, None
    frame = int(0.02 * sr)
    hop = int(0.01 * sr)
    rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop, center=True)[0]
    rms = rms - np.mean(rms)
    if np.allclose(rms.std(), 0):
        return False, 0.0, None
    freqs, pxx = periodogram(rms, fs=sr / hop)
    # frequency window for quarter-note pumping ~0.5–4 Hz
    mask = (freqs >= 0.5) & (freqs <= 4.0)
    if not np.any(mask):
        return False, 0.0, None
    peak_idx = np.argmax(pxx[mask])
    peak_power = pxx[mask][peak_idx]
    peak_freq = freqs[mask][peak_idx]
    # crude threshold: relative prominence vs median
    med = np.median(pxx[mask]) + 1e-9
    prominence = (peak_power / med)
    return (prominence > 12.0), float(min(prominence, 100.0)), float(peak_freq)

def spectral_centroid_hz(y, sr):
    sc = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    return float(np.nan_to_num(np.mean(sc)))

def stereo_width_estimate(path):
    # crude: if file is mono, width=0; if stereo, estimate L-R correlation
    data, sr = sf.read(path, always_2d=True)
    if data.shape[1] < 2:
        return 0.0
    L = data[:,0]; R = data[:,1]
    if np.allclose(L.std(),0) or np.allclose(R.std(),0):
        return 0.0
    corr = np.corrcoef(L, R)[0,1]
    width = 1.0 - max(min(corr, 1.0), -1.0)  # high width = low correlation
    return float(width)

def analyze_stem_characteristics(y, sr):
    """Enhanced spectral analysis for stem-specific tagging"""
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0].mean()
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0].mean()
    zero_crossing = librosa.feature.zero_crossing_rate(y)[0].mean()
    
    # Rhythm analysis for drums
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        onset_strength = librosa.onset.onset_strength(y=y, sr=sr).mean()
    except:
        tempo = 120.0
        onset_strength = 0.0
    
    return {
        "centroid": float(centroid),
        "rolloff": float(rolloff),
        "zero_crossing": float(zero_crossing),
        "tempo": float(tempo),
        "onset_strength": float(onset_strength)
    }

def map_audioset_to_coarse_stem_aware(top_preds, stem_type):
    """
    Enhanced mapping with stem-aware logic
    top_preds: list[(label_str, score_float)]
    stem_type: "drums", "bass", "vocals", "other"
    returns dict coarse_tag -> score (max-aggregated)
    """
    out = {}
    
    if DEBUG:
        print(f"DEBUG: Stem type: {stem_type}")
        print(f"DEBUG: Top AudioSet predictions:")
        for lab, score in top_preds[:10]:
            print(f"  {lab}: {score}")
    
    # Stem-specific keyword mappings
    STEM_KEYWORDS = {
        "drums": ["kick", "snare", "hi-hat", "drum", "percussion", "cymbal", "clap", "thunk"],
        "bass": ["bass", "808", "sub", "low frequency", "electric bass"],
        "vocals": ["singing", "speech", "vocal", "rap", "choir", "chant"],
        "other": ["synthesizer", "piano", "organ", "guitar", "strings", "melody", "pad"]
    }
    
    keywords = STEM_KEYWORDS.get(stem_type, [])
    
    for lab, score in top_preds:
        # Skip stop labels that add zero signal
        if lab.lower() in STOP_LABELS:
            continue
        
        lab_l = lab.lower()
        
        # Try stem-specific keywords first (higher priority)
        stem_mapped = None
        for keyword in keywords:
            if keyword in lab_l:
                stem_mapped = map_keyword_to_tag(keyword, stem_type)
                break
        
        if stem_mapped:
            out[stem_mapped] = max(out.get(stem_mapped, 0.0), float(score))
            if DEBUG:
                print(f"DEBUG: Stem mapping - {lab} -> {stem_mapped} (score: {score})")
            continue
        
        # Try drum labels (for drums stem)
        if stem_type == "drums":
            drum_mapped = None
            for key, coarse in DRUM_LABELS.items():
                if key in lab_l:
                    drum_mapped = coarse
                    break
            
            if drum_mapped:
                out[drum_mapped] = max(out.get(drum_mapped, 0.0), float(score))
                if DEBUG:
                    print(f"DEBUG: Drum mapping - {lab} -> {drum_mapped} (score: {score})")
                continue
        
        # Try instrument labels
        instrument_mapped = None
        for key, coarse in INSTRUMENT_LABELS.items():
            if key in lab_l:
                instrument_mapped = coarse
                break
        
        if instrument_mapped:
            out[instrument_mapped] = max(out.get(instrument_mapped, 0.0), float(score))
            if DEBUG:
                print(f"DEBUG: Instrument mapping - {lab} -> {instrument_mapped} (score: {score})")
            continue
        
        # Fallback to original AUDIOSET_TO_COARSE mapping
        for key, coarse in AUDIOSET_TO_COARSE.items():
            if key in lab_l:
                out[coarse] = max(out.get(coarse, 0.0), float(score))
                if DEBUG:
                    print(f"DEBUG: Fallback mapping - {lab} -> {coarse} (score: {score})")
                break
    
    return out

def map_keyword_to_tag(keyword, stem_type):
    """Map keywords to appropriate tags based on stem type"""
    keyword = keyword.lower()
    
    if stem_type == "drums":
        if "kick" in keyword:
            return "kick"
        elif "snare" in keyword:
            return "snare"
        elif "hi-hat" in keyword or "hi hat" in keyword or "cymbal" in keyword:
            return "hi-hat"
        elif "clap" in keyword:
            return "clap"
        else:
            return "perc_loop"
    
    elif stem_type == "bass":
        if "808" in keyword or "sub" in keyword:
            return "sub_808"
        elif "bass" in keyword:
            return "synth_bass"
        else:
            return "synth_bass"
    
    elif stem_type == "vocals":
        if "rap" in keyword:
            return "vox_rap"
        elif "singing" in keyword:
            return "vox_lead"
        elif "choir" in keyword or "chant" in keyword:
            return "vox_harmony"
        else:
            return "vox"
    
    elif stem_type == "other":
        if "piano" in keyword:
            return "piano"
        elif "organ" in keyword:
            return "organ"
        elif "guitar" in keyword:
            return "pluck"
        elif "strings" in keyword:
            return "lead"
        elif "synthesizer" in keyword or "synth" in keyword:
            return "synth_pad"
        else:
            return "synth_pad"
    
    return None

def add_spectral_fallbacks(tags, characteristics, stem_type):
    """Add spectral analysis-based fallback tags"""
    
    centroid = characteristics["centroid"]
    onset_strength = characteristics["onset_strength"]
    
    if stem_type == "drums":
        # Spectral analysis for drums
        if centroid > 4000:  # Very bright percussion
            tags["hi-hat"] = max(tags.get("hi-hat", 0.0), 0.6)
        elif centroid > 2500:  # Medium bright
            tags["snare"] = max(tags.get("snare", 0.0), 0.5)
        elif centroid > 1500:  # Lower bright
            tags["kick"] = max(tags.get("kick", 0.0), 0.4)
        
        # Rhythm-based fallback
        if onset_strength > 0.3 and not any(tag in tags for tag in ["kick", "snare", "hi-hat", "perc_loop"]):
            tags["perc_loop"] = 0.5
    
    elif stem_type == "bass":
        # Spectral analysis for bass
        if centroid < 2000:  # Low frequency
            tags["sub_808"] = max(tags.get("sub_808", 0.0), 0.6)
        else:  # Higher frequency bass
            tags["synth_bass"] = max(tags.get("synth_bass", 0.0), 0.5)
    
    elif stem_type == "other":
        # Spectral analysis for other instruments
        if centroid > 3000:
            tags["saw_lead"] = max(tags.get("saw_lead", 0.0), 0.5)
        elif centroid < 1500:
            tags["synth_pad"] = max(tags.get("synth_pad", 0.0), 0.5)
        else:
            tags["pluck"] = max(tags.get("pluck", 0.0), 0.4)
    
    return tags

def smart_confidence_calibration(tags, stem_type):
    """Better confidence calibration with stem awareness"""
    
    if not tags:
        return {}
    
    calibrated = {}
    
    # Preserve high confidence scores
    for tag, score in tags.items():
        if score > 0.7:  # High confidence - preserve
            calibrated[tag] = score
        elif score > 0.3:  # Medium confidence - slight boost
            calibrated[tag] = min(1.0, score * 1.2)
        elif score > 0.15:  # Low confidence - keep but don't boost
            calibrated[tag] = score
        # Filter out very low confidence
    
    # Ensure minimum tags per stem type
    if stem_type == "drums" and not any(t in calibrated for t in ["kick", "snare", "hi-hat", "perc_loop"]):
        calibrated["perc_loop"] = 0.4  # Fallback
    
    if stem_type == "bass" and not any(t in calibrated for t in ["sub_808", "synth_bass", "reese"]):
        calibrated["synth_bass"] = 0.4  # Fallback
    
    if stem_type == "other" and not any(t in calibrated for t in ["synth_pad", "saw_lead", "pluck"]):
        calibrated["synth_pad"] = 0.4  # Fallback
    
    return calibrated

def separate_meta_content_tags(tags_dict):
    """
    Separate meta tags (stereo_wide, sidechain_pump) from content tags (instruments)
    """
    meta_tags = {}
    content_tags = {}
    
    meta_tag_names = {"stereo_wide", "sidechain_pump"}
    
    for tag, score in tags_dict.items():
        if tag in meta_tag_names:
            meta_tags[tag] = score
        else:
            content_tags[tag] = score
    
    return content_tags, meta_tags

def tag_stem(path, at_model, global_sidechain=False):
    # Determine stem type from filename
    stem_name = Path(path).stem.lower()
    if "drum" in stem_name:
        stem_type = "drums"
    elif "bass" in stem_name:
        stem_type = "bass"
    elif "vocal" in stem_name:
        stem_type = "vocals"
    else:
        stem_type = "other"
    
    y, sr = load_audio_mono(path, sr=32000)
    centroid = spectral_centroid_hz(y, 32000)
    width = stereo_width_estimate(path)
    
    # Enhanced spectral analysis
    characteristics = analyze_stem_characteristics(y, sr)

    # PANNs inference
    (clipwise_output, _) = at_model.inference(y[None, :])
    clipwise_output = clipwise_output[0]  # shape: (527,)
    # Take top-k above threshold
    idxs = np.argsort(-clipwise_output)[:32]
    preds = [(labels[i], float(clipwise_output[i])) for i in idxs if clipwise_output[i] >= MIN_SCORE]
    preds = preds[:DEFAULT_TOPK]

    # Stem-aware mapping
    coarse = map_audioset_to_coarse_stem_aware(preds, stem_type)

    # Add spectral fallbacks
    coarse = add_spectral_fallbacks(coarse, characteristics, stem_type)

    # synth refinement
    fam = refine_synth_family(preds, centroid_hz=centroid, is_wide_stereo=(width>0.25))
    if fam:
        coarse[fam] = max(coarse.get(fam, 0.0), 0.5)

    # Only detect sidechain on individual stems if not doing global detection
    if not global_sidechain:
        sc_bool, sc_prom, sc_hz = detect_sidechain_pump(y, 32000)
        if sc_bool:
            coarse["sidechain_pump"] = min(1.0, 0.2 + np.log10(sc_prom+1e-9))  # squashed score

    # Add stereo width as meta tag if significant
    if width > 0.25:
        coarse["stereo_wide"] = min(1.0, width)

    # Apply smart confidence calibration
    calibrated = smart_confidence_calibration(coarse, stem_type)
    
    # Separate meta and content tags
    content_tags, meta_tags = separate_meta_content_tags(calibrated)
    
    # Take top K content tags (allow multiple per stem)
    top_content = sorted(content_tags.items(), key=lambda x: -x[1])[:TOP_K_TAGS]
    top_content = [{"label": k, "score": round(v, 2)} for k, v in top_content if v >= CONTENT_MIN_SCORE]
    
    # Format meta tags
    meta_tags_list = [{"label": k, "score": v} for k, v in sorted(meta_tags.items(), key=lambda x: -x[1])]

    return {
        "file": str(path),
        "spectral_centroid_hz": centroid,
        "stereo_width": width,
        "top_audioset": preds,
        "content_tags": top_content,
        "meta_tags": meta_tags_list
    }

def detect_global_sidechain(clip_dir):
    """
    Compute RMS pump on the sum of all stems (or original clip if available)
    Returns: (has_pump, strength, frequency)
    """
    stems = ["drums.wav", "bass.wav", "vocals.wav", "other.wav"]
    stem_paths = [clip_dir / stem for stem in stems]
    
    # Load and sum all available stems
    summed_audio = None
    for stem_path in stem_paths:
        if stem_path.exists():
            y, sr = load_audio_mono(stem_path, sr=32000)
            if summed_audio is None:
                summed_audio = y
            else:
                # Pad to same length if needed
                max_len = max(len(summed_audio), len(y))
                if len(summed_audio) < max_len:
                    summed_audio = np.pad(summed_audio, (0, max_len - len(summed_audio)))
                if len(y) < max_len:
                    y = np.pad(y, (0, max_len - len(y)))
                summed_audio += y
    
    if summed_audio is None:
        return False, 0.0, None
    
    # Normalize the sum
    if np.max(np.abs(summed_audio)) > 0:
        summed_audio = summed_audio / np.max(np.abs(summed_audio))
    
    return detect_sidechain_pump(summed_audio, 32000)

def tag_clip_folder(clip_dir: Path, out_json: Path):
    at = AudioTagging(checkpoint_path=None, device="cpu")  # downloads model if not cached
    
    # Detect global sidechain first
    global_sc_bool, global_sc_strength, global_sc_freq = detect_global_sidechain(clip_dir)
    
    results = []
    for stem in ["drums.wav","bass.wav","vocals.wav","other.wav"]:
        stem_path = clip_dir / stem
        if stem_path.is_file():
            # Pass global sidechain flag to avoid per-stem spam
            result = tag_stem(stem_path, at, global_sidechain=True)
            results.append(result)
    
    # Add global sidechain to metadata if detected
    metadata = {}
    if global_sc_bool:
        metadata["global_sidechain"] = {
            "detected": True,
            "strength": min(1.0, 0.2 + np.log10(global_sc_strength+1e-9)),
            "frequency_hz": global_sc_freq
        }
    else:
        metadata["global_sidechain"] = {"detected": False}
    
    out = {
        "clip": clip_dir.name,
        "metadata": metadata,
        "results": results
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[OK] Wrote {out_json}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clip_name", help="Folder name under /app/audio_outputs (e.g., 'test')")
    ap.add_argument("--outputs_root", default=AUDIO_OUTPUTS)
    args = ap.parse_args()

    clip_dir = Path(args.outputs_root) / args.clip_name
    if not clip_dir.is_dir():
        raise SystemExit(f"Clip folder not found: {clip_dir}")

    out_json = clip_dir / "tags.json"
    tag_clip_folder(clip_dir, out_json) 