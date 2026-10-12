"""Offline CPU-only STT; owned subprocess permits cancellation of native inference."""
import asyncio
import json
import struct
import sys
from pathlib import Path


class LocalWhisper:
    def __init__(self, model):
        self.model = Path(model)
        self.process = None

    async def start(self):
        if not self.model.is_dir() or not (self.model / "model.bin").is_file():
            raise ValueError("Local model unavailable")
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.integrations.stt.local_whisper_worker", str(self.model),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=8192)
        ready = await asyncio.wait_for(self.process.stdout.readline(), 15)
        if json.loads(ready) != {"ready": True}:
            raise ValueError("Local model unavailable")

    async def transcribe(self, pcm):
        if not self.process or not 0 < len(pcm) <= 64000 or len(pcm) % 2:
            raise ValueError("Invalid audio")
        self.process.stdin.write(struct.pack("!I", len(pcm)) + pcm)
        await self.process.stdin.drain()
        line = await asyncio.wait_for(self.process.stdout.readline(), 15)
        value = json.loads(line)
        if set(value) != {"text"} or not isinstance(value["text"], str) or len(value["text"]) > 1000:
            raise ValueError("Invalid caption")
        return value["text"]

    async def close(self):
        if self.process:
            if self.process.returncode is None:
                self.process.kill()
            await self.process.wait()
            self.process = None
