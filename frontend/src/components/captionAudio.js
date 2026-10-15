// Only runs after the server's two-party consent gate opens. No recording/files.
class CaptionAudio extends AudioWorkletProcessor {
  constructor() {
    super(); this.samples = new Int16Array(1600); this.index = 0;
    this.running = true; this.muted = true; this.captured = 0;
    this.port.onmessage = e => {
      if (e.data?.kind === "mute") {
        this.muted = !!e.data.value; this.samples.fill(0); this.index = 0;
      } else if (e.data?.kind === "flush" && this.running) {
        this.running = false;
        if (this.index && !this.muted) {
          const tail = this.samples.slice(0, this.index);
          this.port.postMessage(tail.buffer, [tail.buffer]);
        }
        this.samples.fill(0); this.index = 0;
        this.port.postMessage({kind:"flushed", captured_samples:this.captured});
      }
    };
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (channel && this.running) this.captured += channel.length;
    if (channel && this.running && !this.muted) for (const sample of channel) {
      this.samples[this.index++] = Math.round(Math.max(-1, Math.min(1, sample)) * 32767);
      if (this.index === 1600) {
        this.port.postMessage(this.samples.buffer, [this.samples.buffer]);
        this.samples = new Int16Array(1600); this.index = 0;
      }
    }
    return true;
  }
}
registerProcessor("caption-audio", CaptionAudio);
