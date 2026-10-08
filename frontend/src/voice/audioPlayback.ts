export interface Player {
  /** Must be called from a user gesture so later playback is allowed by autoplay policy. */
  unlock(): void;
  /** Queues audio for `generation`; audio from any other generation is discarded. */
  enqueue(samples: Float32Array, sampleRate: number, generation: number): number | null;
  /** Stops everything and starts a new generation. */
  reset(generation: number): void;
  /** Resolves when every queued buffer of the current generation has finished playing. */
  drained(): Promise<void>;
  /** Seconds of audio scheduled but not yet played (for synthesis backpressure). */
  bufferedSeconds(): number;
  level(): number;
  dispose(): void;
}

// Plays synthesized chunks back to back through an analyser, so the mascot's mouth follows
// the real output amplitude.
export class WebAudioPlayer implements Player {
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private generation = 0;
  private nextStart = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private waiters: (() => void)[] = [];
  private meterBuffer = new Float32Array(1024);

  private ensure(): AudioContext {
    if (!this.context) {
      this.context = new AudioContext();
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.connect(this.context.destination);
    }
    return this.context;
  }

  unlock() {
    void this.ensure().resume().catch(() => undefined);
  }

  enqueue(samples: Float32Array, sampleRate: number, generation: number): number | null {
    if (generation !== this.generation || !samples.length) return null;
    const context = this.ensure();
    const buffer = context.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples, 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyser!);
    const start = Math.max(context.currentTime + 0.03, this.nextStart);
    source.start(start);
    this.nextStart = start + buffer.duration;
    this.sources.add(source);
    source.onended = () => {
      this.sources.delete(source);
      if (!this.sources.size) this.flushWaiters();
    };
    return performance.timeOrigin + performance.now() + (start - context.currentTime) * 1000; // absolute time it becomes audible
  }

  private flushWaiters() {
    const waiters = this.waiters;
    this.waiters = [];
    waiters.forEach((resolve) => resolve());
  }

  reset(generation: number) {
    this.generation = generation;
    for (const source of this.sources) {
      source.onended = null;
      try { source.stop(); } catch { /* already stopped */ }
    }
    this.sources.clear();
    this.nextStart = 0;
    this.flushWaiters();
  }

  drained(): Promise<void> {
    if (!this.sources.size) return Promise.resolve();
    return new Promise((resolve) => this.waiters.push(resolve));
  }

  bufferedSeconds(): number {
    if (!this.context || !this.sources.size) return 0;
    return Math.max(0, this.nextStart - this.context.currentTime);
  }

  level(): number {
    if (!this.analyser || !this.sources.size) return 0;
    this.analyser.getFloatTimeDomainData(this.meterBuffer);
    let sum = 0;
    for (const value of this.meterBuffer) sum += value * value;
    return Math.min(1, Math.sqrt(sum / this.meterBuffer.length) * 5);
  }

  dispose() {
    this.reset(this.generation + 1);
    void this.context?.close().catch(() => undefined);
    this.context = null;
    this.analyser = null;
  }
}
