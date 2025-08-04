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

def map_audioset_to_coarse(top_preds):
    """
    top_preds: list[(label_str, score_float)]
    returns dict coarse_tag -> score (max-aggregated)
    """
    out = {}
    
    if DEBUG:
        print(f"DEBUG: Top AudioSet predictions:")
        for lab, score in top_preds[:10]:  # Show top 10
            print(f"  {lab}: {score}")
    
    for lab, score in top_preds:
        # Skip stop labels that add zero signal
        if lab.lower() in STOP_LABELS:
            continue
        
        lab_l = lab.lower()
        
        # Try drum labels first (higher priority)
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
    y, sr = load_audio_mono(path, sr=32000)
    centroid = spectral_centroid_hz(y, 32000)
    width = stereo_width_estimate(path)

    # PANNs inference
    (clipwise_output, _) = at_model.inference(y[None, :])
    clipwise_output = clipwise_output[0]  # shape: (527,)
    # Take top-k above threshold
    idxs = np.argsort(-clipwise_output)[:32]
    preds = [(labels[i], float(clipwise_output[i])) for i in idxs if clipwise_output[i] >= MIN_SCORE]
    preds = preds[:DEFAULT_TOPK]

    coarse = map_audioset_to_coarse(preds)

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

    # Apply confidence calibration
    calibrated = calibrate_confidence(coarse, min_score=0.15)
    
    # Add drum-specific heuristics based on spectral centroid
    if "perc_loop" in calibrated and centroid > 2000:  # High centroid = bright percussion
        if centroid > 3000:
            calibrated["hi-hat"] = max(calibrated.get("hi-hat", 0.0), 0.60)  # Very bright = hi-hat
        elif centroid > 2500:
            calibrated["snare"] = max(calibrated.get("snare", 0.0), 0.50)  # Medium bright = snare
        else:
            calibrated["kick"] = max(calibrated.get("kick", 0.0), 0.40)  # Lower bright = kick
    
    # Ensure organ detection works - preserve organ if detected
    if "organ" in coarse and "organ" not in calibrated:
        calibrated["organ"] = max(coarse.get("organ", 0.0), 0.47)  # Ensure organ is preserved
    
    # Add kick/snare heuristics for drums stem (high centroid suggests bright percussion)
    if "perc_loop" in calibrated and centroid > 3000:  # Very bright percussion
        calibrated["snare"] = max(calibrated.get("snare", 0.0), 0.45)  # Likely snare at this brightness
    
    # Separate meta and content tags
    content_tags, meta_tags = separate_meta_content_tags(calibrated)
    
    # Take top K content tags (allow multiple per stem)
    top_content = sorted(content_tags.items(), key=lambda x: -x[1])[:TOP_K_TAGS]
    top_content = [{"label": k, "score": round(v, 2)} for k, v in top_content if v >= CONTENT_MIN_SCORE]  # min confidence + round to 2 decimals
    
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