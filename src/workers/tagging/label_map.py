# Minimal, extensible mapping from AudioSet -> coarse tags used in your app.

# Updated tag schema v0.2 - keep it < 30 total for F1 tracking
COARSE_TAGS = {
    # Drums
    "kick", "snare", "hi-hat", "clap", "perc_loop",
    # Bass  
    "sub_808", "reese", "synth_bass", "slap_bass",
    # Keys
    "piano", "rhodes", "organ", "bell", "pluck",
    # Vocals
    "vox", "vox_lead", "vox_rap", "vox_harmony",
    # FX
    "riser", "impact", "vinyl_noise",
    # Meta
    "sidechain_pump", "stereo_wide"
}

# Labels that add zero signal - filter these out
STOP_LABELS = {
    "music",  # always top-1, adds zero signal
    # Removed "speech" so it can be mapped to vocal tags
}

# Comprehensive drum label mappings
DRUM_LABELS = {
    "kick drum": "kick",
    "bass drum": "kick", 
    "kick": "kick",
    "snare drum": "snare",
    "snare": "snare",
    "hi-hat": "hi-hat",
    "hi hat": "hi-hat",
    "hihat": "hi-hat",
    "cymbal": "hi-hat",
    "ride cymbal": "hi-hat",
    "crash cymbal": "hi-hat",
    "tom-tom": "perc_loop",
    "clap": "clap",
    "hand clap": "clap",
    "thunk": "perc_loop",
    "percussion": "perc_loop",
    "drum machine": "perc_loop",
}

# Comprehensive instrument label mappings
INSTRUMENT_LABELS = {
    "organ": "organ",
    "hammond organ": "organ",
    "electronic organ": "organ",
    "piano": "piano",
    "electric piano": "rhodes",
    "rhodes": "rhodes",
    "harpsichord": "bell",
    "bell": "bell",
    "glockenspiel": "bell",
    "acoustic guitar": "pluck",
    "electric guitar": "pluck",
    "violin": "lead",
    "cello": "lead",
    "strings": "lead",
    "synthesizer": "pluck",
    "sampler": "pluck",
    "singing": "vox_lead",
    "synthetic singing": "vox_lead",
    "choir": "vox_harmony",
    "vocal": "vox",
    "a capella": "vox_lead",
    "speech": "vox_rap",
    "rap": "vox_rap",
    "chant": "vox_harmony",
    "electric bass": "synth_bass",
    "bass guitar": "synth_bass",
    "synth bass": "synth_bass",
    "808": "sub_808",
    "sub": "sub_808",
    "sub bass": "sub_808",
}

# Map subsets of AudioSet labels (lowercased) to coarse tags
AUDIOSET_TO_COARSE = {
    # Drums - COMPREHENSIVE MAPPING
    "drum": "perc_loop",
    "drum kit": "perc_loop", 
    "snare drum": "snare",
    "snare": "snare",
    "bass drum": "kick",
    "kick drum": "kick",
    "kick": "kick",  # catch variations
    "hi-hat": "hi-hat",
    "hi hat": "hi-hat",  # catch space variations
    "hihat": "hi-hat",  # catch no-space variations
    "cymbal": "hi-hat",
    "ride cymbal": "hi-hat",
    "crash cymbal": "hi-hat",
    "tom-tom": "perc_loop",
    "clap": "clap",
    "hand clap": "clap",
    "thunk": "perc_loop",  # catch percussive hits
    "percussion": "perc_loop",  # catch generic percussion
    "drum machine": "perc_loop",  # catch electronic drums

    # Bass - EXPANDED
    "electric bass": "synth_bass",
    "bass guitar": "synth_bass", 
    "synth bass": "synth_bass",
    "808": "sub_808",  # catch 808 references
    "sub": "sub_808",
    "sub bass": "sub_808",
    "bass": "synth_bass",  # Generic bass catch
    "low frequency": "synth_bass",  # Low frequency content

    # Keys / Piano / Organ - KEEP USEFUL ONES
    "piano": "piano",
    "electric piano": "rhodes",
    "rhodes": "rhodes",
    "organ": "organ",
    "hammond organ": "organ",
    "electronic organ": "organ",
    "musical instrument": "organ",  # often maps to organ-like content
    "keyboard (musical)": "piano",
    "harpsichord": "bell",
    "bell": "bell",
    "glockenspiel": "bell",

    # Guitars / Strings
    "acoustic guitar": "pluck",
    "electric guitar": "pluck",
    "violin": "lead",  # treat as melodic
    "cello": "lead",
    "strings": "lead",

    # Synths (broad) - EXPANDED
    "synthesizer": "synth_pad",    # default to pad, refine with heuristics
    "sampler": "synth_pad",
    "electronic": "synth_pad",      # catch electronic music
    "electronic music": "synth_pad", # catch electronic music
    "melody": "saw_lead",           # melodic content
    "lead": "saw_lead",             # lead sounds
    "pad": "synth_pad",             # pad sounds
    "atmosphere": "synth_pad",       # atmospheric content
    "ambient": "synth_pad",         # ambient content
    "texture": "synth_pad",         # textural content

    # Vocals - EXPANDED with subtypes
    "singing": "vox_lead",
    "synthetic singing": "vox_lead",
    "choir": "vox_harmony",
    "vocal": "vox",
    "a capella": "vox_lead",
    "speech": "vox_lead",  # Changed from vox_rap to vox_lead
    "rap": "vox_rap",
    "chant": "vox_harmony",

    # FX - EXPANDED
    "reverberation": "vinyl_noise",  # treat as texture
    "echo": "vinyl_noise",
    "chorus effect": "vinyl_noise",
    "distortion": "impact",
    "overdrive": "impact",
    "saturation": "impact",
    
    # Additional Electronic Music Mappings
    "techno": "synth_pad",
    "house": "synth_pad",
    "trance": "synth_pad",
    "ambient music": "synth_pad",
    "electronic": "synth_pad",
    "synthesizer": "synth_pad",
    "keyboard": "synth_pad",
    "synthesizer (musical)": "synth_pad",
}

# Confidence calibration and filtering
def calibrate_confidence(scores_dict, min_score=0.10):  # Lowered from 0.15 to 0.10
    """
    Quick confidence calibration: min-max rescale per-stem, 
    then zero-out anything < threshold
    """
    if not scores_dict:
        return {}
    
    # Get min/max for rescaling
    all_scores = list(scores_dict.values())
    min_val = min(all_scores)
    max_val = max(all_scores)
    
    # Avoid division by zero
    if max_val == min_val:
        return scores_dict
    
    # Rescale to 0-1 range and round to 2 decimal places
    calibrated = {}
    for tag, score in scores_dict.items():
        rescaled = (score - min_val) / (max_val - min_val)
        if rescaled >= min_score:
            calibrated[tag] = round(rescaled, 2)  # Round to 2 decimal places
    
    return calibrated

# Optional heuristics to refine synth family:
def refine_synth_family(top_labels, centroid_hz, is_wide_stereo):
    """
    Crude heuristics: if 'synthesizer' present and spectrum is bright with wide stereo → saw lead.
    If dark and sustained → pad. Short decay + bright → pluck.
    """
    labs = {l for l,_ in top_labels}
    if any("synth" in l for l in labs):
        if centroid_hz > 3000 and is_wide_stereo:
            return "saw_lead"
        # crude split on centroid
        if centroid_hz < 1200:
            return "synth_pad"
        return "pluck"
    return None 