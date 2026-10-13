"""Private in-memory pipe; no files, logs, downloads or remote STT calls."""
import os
import sys
from app.integrations.stt.local_whisper import MAX_CHUNK_BYTES


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import json
    import struct
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel(sys.argv[1], device="cpu", compute_type="int8",
                         local_files_only=True, cpu_threads=2, num_workers=1)
    print(json.dumps({"ready": True}), flush=True)
    while header := sys.stdin.buffer.read(4):
        if len(header) != 4:
            return
        size = struct.unpack("!I", header)[0]
        if not 0 < size <= MAX_CHUNK_BYTES or size % 2:
            return
        pcm = sys.stdin.buffer.read(size)
        if len(pcm) != size:
            return
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        # Default temperature fallback can decode a cut speech boundary six times.
        # This bounded live proof uses one greedy pass, not hidden decoding retries.
        segments, _ = model.transcribe(samples, language="en", beam_size=1, temperature=0.0,
                                      vad_filter=True, condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments)[:1000]
        print(json.dumps({"text": text}), flush=True)
        del pcm, samples, segments, text


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1) from None
