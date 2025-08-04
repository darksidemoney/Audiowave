import os, argparse, sys
from pathlib import Path
import torch
import torchaudio
from demucs.pretrained import get_model
from demucs.apply import apply_model
from demucs.audio import AudioFile

def separate_file(in_path: Path, out_root: Path, model_name: str = "htdemucs", device: str = "cpu"):
    model = get_model(name=model_name)
    model.to(device)
    model.eval()

    wav = AudioFile(str(in_path)).read(streams=0, samplerate=model.samplerate, channels=2)
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)

    with torch.no_grad():
        sources = apply_model(model, wav[None].to(device), device=device)[0].cpu()
    stems = model.sources

    out_dir = out_root / in_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    for src_name, src_audio in zip(stems, sources):
        out_path = out_dir / f"{src_name}.wav"
        torchaudio.save(str(out_path), src_audio, model.samplerate)
        print(f"Saved: {out_path}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input", help="Path to input audio (mp3/wav)")
    p.add_argument("--inputs_dir", default="/app/audio_inputs")
    p.add_argument("--outputs_dir", default="/app/audio_outputs")
    p.add_argument("--model", default=os.getenv("DEMUCS_MODEL", "htdemucs"))
    p.add_argument("--device", default=os.getenv("DEMUCS_DEVICE", "cpu"))
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        # allow basename relative to inputs_dir
        alt = Path(args.inputs_dir) / args.input
        if alt.is_file():
            in_path = alt
        else:
            print(f"Input not found: {args.input}")
            sys.exit(1)

    separate_file(in_path, Path(args.outputs_dir), args.model, args.device) 