// Only runs after the server's two-party consent gate opens. No recording/files.
class CaptionAudio extends AudioWorkletProcessor {
  constructor() { super(); this.samples = new Int16Array(1600); this.index = 0; }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (channel) for (const sample of channel) {
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
