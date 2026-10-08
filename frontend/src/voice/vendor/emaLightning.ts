/*
 * EMA Lightning Turkish TTS engine for onnxruntime-web.
 *
 * Ported to TypeScript from web/tts.js and web/normalizer.js of
 * https://huggingface.co/ozcancelik/ema-lightning-onnx at revision
 * 13c431db0356b2f7fafb1247cd823ec0d777c820 (Apache License 2.0; see
 * public/third-party/ema-lightning-onnx/ for LICENSE and NOTICE).
 *
 * Modifications by modAI-stack:
 * - onnxruntime-web is the bundled npm package served from the application origin instead of
 *   a CDN import; model files are fetched from self-hosted, revision-pinned URLs.
 * - Model bytes are cached under a revision-specific Cache Storage name.
 * - The per-word timing callback (onPiece) and wavBlob() are omitted; type annotations added.
 *   The text frontend, chunker, frame planner, noise and windowed decoding are unchanged.
 */
import * as ort from "onnxruntime-web/webgpu";

export const RATE = 48000;
const FIRST_WINDOW = 25; // first decoded window is one second, so audio starts early
const WINDOW = 100; // then four seconds at a time
const CONTEXT = 8; // frames decoded on each side of a window
const MAX_WORD_FRAMES = 250;
const MAX_FRAMES = 3000;

export type EmaBackend = "webgpu" | "wasm";
export type EmaProgress = (stage: string, fraction: number) => void;

interface EmaMeta {
  vocab: string[];
  times: number[];
  latent_dim: number;
  hop: number;
  sample_rate: number;
}

export interface EmaStats {
  pieces?: string[];
  text?: number;
  sound?: number;
  decode?: number;
}

// ---------- model bytes (Cache Storage, revision-specific) ----------

async function bytes(url: string, cacheName: string): Promise<ArrayBuffer> {
  let cache: Cache | null = null;
  try {
    cache = await caches.open(cacheName);
  } catch {
    // No Cache Storage outside a secure context: plain fetch.
  }
  const hit = await cache?.match(url).catch(() => undefined);
  if (hit) return hit.arrayBuffer();
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  try {
    await cache?.put(url, response.clone());
  } catch {
    // Full storage: still works, just not cached.
  }
  return response.arrayBuffer();
}

// ---------- normalizer-tr as WebAssembly (web/normalizer.js) ----------

type Normalize = (text: string) => string;

interface NormalizerExports {
  memory: WebAssembly.Memory;
  alloc(length: number): number;
  dealloc(pointer: number, length: number): void;
  normalize(pointer: number, length: number): void;
  result_ptr(): number;
  result_len(): number;
}

async function loadNormalizer(source: ArrayBuffer): Promise<Normalize> {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const { instance } = await WebAssembly.instantiate(source, {});
  const w = instance.exports as unknown as NormalizerExports;
  return (text) => {
    const input = encoder.encode(text);
    const pointer = w.alloc(input.length);
    new Uint8Array(w.memory.buffer, pointer, input.length).set(input);
    w.normalize(pointer, input.length);
    w.dealloc(pointer, input.length);
    return decoder.decode(new Uint8Array(w.memory.buffer, w.result_ptr(), w.result_len()));
  };
}

// ---------- text frontend (frontend.py) ----------

const TURKISH = new Set("çğıöşüÇĞİÖŞÜ");
const TYPOGRAPHY: Record<string, string> = { "’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'", "“": '"', "”": '"', "„": '"',
  "«": '"', "»": '"', "–": "-", "—": "-", "−": "-", "…": "..." };
// eslint-disable-next-line no-control-regex
const UNSAFE = /[\x00-\x08\x0b-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]/g;

const BLOCK_BYTES = 8 * 1024;

// Split at whitespace into pieces the normalizer accepts in one call.
function blocks(text: string): string[] {
  const out: string[] = [];
  const encoder = new TextEncoder();
  let block: string[] = [];
  let size = 0;
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const n = encoder.encode(word).length + 1;
    if (block.length && size + n > BLOCK_BYTES) { out.push(block.join(" ")); block = []; size = 0; }
    block.push(word);
    size += n;
  }
  if (block.length) out.push(block.join(" "));
  return out;
}

export function frontend(text: string, vocab: Set<string>, normalize: Normalize): string {
  text = text.replace(UNSAFE, " ");
  if (!text.trim()) return "";
  return alphabet(blocks(text).map(normalize).join(" "), vocab);
}

export function alphabet(text: string, vocab: Set<string>): string {
  text = text.replace(UNSAFE, " ");
  text = [...text].map((ch) => TYPOGRAPHY[ch] ?? ch).join("");
  text = text.replace(/İ/g, "i").replace(/I/g, "ı").toLocaleLowerCase("tr");
  let out = "";
  for (let ch of text) {
    if (!TURKISH.has(ch)) ch = ch.normalize("NFKD").replace(/\p{M}/gu, "");
    out += ch && [...ch].every((c) => vocab.has(c)) ? ch : " ";
  }
  return out.replace(/\s+/g, " ").trim();
}

// ---------- chunker.py ----------

const LETTERS_PER_SECOND = 18, MAX_SECONDS = 10, MAX_LETTERS = 250;
const SENTENCE_PAUSE = 0.25, CLAUSE_PAUSE = 0.12;
const CUTS: [RegExp, number][] = [[/[.!?]+["')]*(?= )/g, SENTENCE_PAUSE], [/[,;:](?= )/g, CLAUSE_PAUSE], [/\S(?= )/g, CLAUSE_PAUSE]];

function finish(piece: string): string {
  if (/[.!?]$/.test(piece.replace(/["')]+$/, ""))) return piece;
  return piece.replace(/[,;:\- ]+$/, "") + ".";
}

export function chunk(text: string, speed: number): [string, number][] {
  const limit = Math.floor(Math.min(MAX_LETTERS, LETTERS_PER_SECOND * MAX_SECONDS * speed));
  const pieces: [string, number][] = [];
  let rest = text.trim();
  while (rest) {
    let cut = rest.length, pause = 0;
    if (rest.length > limit) {
      cut = limit;
      const head = rest.slice(0, limit + 1); // finditer(rest, 0, limit + 1): lookahead stops there too
      for (const [pattern, gap] of CUTS) {
        const ends = [...head.matchAll(pattern)].map((m) => (m.index ?? 0) + m[0].length);
        if (ends.length) { cut = ends[ends.length - 1]; pause = gap; break; }
      }
    }
    const piece = rest.slice(0, cut).trim();
    rest = rest.slice(cut).trim();
    if (/\p{L}/u.test(piece)) pieces.push([finish(piece), pause]);
  }
  if (pieces.length) pieces[pieces.length - 1][1] = 0;
  return pieces;
}

// ---------- seeded Gaussian noise ----------

function gaussian(seed: number): (n: number) => Float32Array {
  let a = seed >>> 0;
  const uniform = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return (n) => {
    const out = new Float32Array(n);
    for (let i = 0; i < n; i += 2) {
      const r = Math.sqrt(-2 * Math.log(1 - uniform())), th = 2 * Math.PI * uniform();
      out[i] = r * Math.cos(th);
      if (i + 1 < n) out[i + 1] = r * Math.sin(th);
    }
    return out;
  };
}

// ---------- engine.py ----------

function words(text: string): { cw: number[]; wstart: number[] } {
  // word index of each letter, and the first letter of that word (spaces belong to the next word)
  const starts: number[] = [];
  for (let i = 0; i < text.length; i++) if (text[i] !== " " && (i === 0 || text[i - 1] === " ")) starts.push(i);
  if (!starts.length) starts.push(0);
  const bounds = [0, ...starts.slice(1), text.length];
  const cw: number[] = [], wstart: number[] = [];
  for (let w = 0; w + 1 < bounds.length; w++)
    for (let i = bounds[w]; i < bounds[w + 1]; i++) { cw.push(w); wstart.push(bounds[w]); }
  return { cw, wstart };
}

function plan(cw: number[], wstart: number[], dur: Float32Array, speed: number) {
  const L = cw.length, nWords = cw[L - 1] + 1;
  const d = Float32Array.from(dur, (x) => x / speed);
  const sums = new Float64Array(nWords);
  for (let i = 0; i < L; i++) sums[cw[i]] += d[i];
  const counts = Array.from(sums, (s) => Math.min(MAX_WORD_FRAMES, Math.max(1, Math.round(s))));
  const T = Math.min(counts.reduce((x, y) => x + y, 0), MAX_FRAMES);
  const fw = new Int32Array(T), fp = new Float32Array(T);
  for (let w = 0, f = 0; w < nWords; w++) {
    for (let j = 0; j < counts[w] && f < T; j++, f++) { fw[f] = w; fp[f] = j / counts[w]; }
  }
  // sound_stage: where each letter sits inside its word, by duration
  const c = Float32Array.from(d, (x) => Math.max(x, 1e-4));
  const done = new Float32Array(L), total = new Float32Array(nWords);
  for (let i = 0, acc = 0; i < L; i++) { acc += c[i]; done[i] = acc; total[cw[i]] += c[i]; }
  const before = (i: number) => done[i] - c[i];
  // aligner letter_pos: global positions measured in letters
  const wlen = new Float32Array(nWords);
  for (const w of cw) wlen[w] += 1;
  const woff = new Float32Array(nWords);
  for (let w = 1; w < nWords; w++) woff[w] = woff[w - 1] + Math.max(wlen[w - 1], 1);
  const cg = new Float32Array(L), fg = new Float32Array(T);
  for (let i = 0; i < L; i++) {
    const cp = Math.min(1, Math.max(0, (done[i] - before(wstart[i]) - 0.5 * c[i]) / Math.max(total[cw[i]], 1e-8)));
    cg[i] = woff[cw[i]] + cp * Math.max(wlen[cw[i]], 1);
  }
  for (let f = 0; f < T; f++) fg[f] = woff[fw[f]] + fp[f] * Math.max(wlen[fw[f]], 1);
  return { T, fw, cg, fg };
}

function windows(frames: number, first: number): [number, number][] {
  const spans: [number, number][] = [];
  for (let s = 0; s < frames;) {
    const e = Math.min(frames, s + (s === 0 ? first : WINDOW));
    spans.push([s, e]);
    s = e;
  }
  return spans;
}

const i64 = (arr: ArrayLike<number>) => new ort.Tensor("int64", BigInt64Array.from(arr as number[], (x) => BigInt(x)), [1, arr.length]);
const f32 = (arr: Float32Array, dims: number[]) => new ort.Tensor("float32", arr, dims);

export class EmaLightning {
  private readonly stoi: Map<string, number>;
  private readonly alpha: Set<string>;

  private constructor(
    private readonly meta: EmaMeta,
    private readonly text: ort.InferenceSession,
    private readonly sound: ort.InferenceSession,
    private readonly decoder: ort.InferenceSession,
    private readonly normalize: Normalize,
    readonly backend: EmaBackend,
  ) {
    this.stoi = new Map(meta.vocab.map((ch, i) => [ch, i]));
    this.alpha = new Set(meta.vocab.filter((v) => v.length === 1));
  }

  // fp32 graphs, as the upstream default: fp16 text/decoder graphs are wrong on WebGPU.
  static async load(backend: EmaBackend, base: string, cacheName: string, onProgress: EmaProgress = () => {}): Promise<EmaLightning> {
    const meta = (await (await fetch(base + "meta.json")).json()) as EmaMeta;
    const options: ort.InferenceSession.SessionOptions = {
      executionProviders: backend === "webgpu" ? ["webgpu", "wasm"] : ["wasm"],
      graphOptimizationLevel: "all",
    };
    onProgress("normalizer", 0);
    const normalize = await loadNormalizer(await bytes(base + "normalizer.wasm", cacheName));
    const names = ["text", "sound", "decoder"] as const;
    const sessions: ort.InferenceSession[] = [];
    for (const [i, name] of names.entries()) {
      onProgress(name, (i + 1) / (names.length + 1));
      sessions.push(await ort.InferenceSession.create(await bytes(base + name + ".onnx", cacheName), options));
    }
    onProgress("ready", 1);
    return new EmaLightning(meta, sessions[0], sessions[1], sessions[2], normalize, backend);
  }

  // frees the sessions' wasm and GPU memory; the object cannot be used afterwards
  async release(): Promise<void> {
    for (const session of [this.text, this.sound, this.decoder]) await session.release().catch(() => undefined);
  }

  pieces(text: string, speed: number): [string, number][] {
    return chunk(frontend(text, this.alpha, this.normalize), speed);
  }

  // Yields Float32Array chunks of 48 kHz audio as they are made; `stats` gets per-stage timings.
  async *stream(text: string, { speed = 1, seed = 0, stats = {} as EmaStats } = {}): AsyncGenerator<Float32Array> {
    const pieces = this.pieces(text, speed);
    stats.pieces = pieces.map(([piece]) => piece);
    stats.text = stats.sound = stats.decode = 0;
    const nSteps = this.meta.times.length, D = this.meta.latent_dim, hop = this.meta.hop;
    for (let k = 0; k < pieces.length; k++) {
      const [piece, pause] = pieces[k];
      let t0 = performance.now();
      const ids = [...piece].map((ch) => this.stoi.get(ch) ?? 1);
      const { cw, wstart } = words(piece);
      const { h, dur } = await this.text.run({ ids: i64(ids) });
      const durations = (await dur.getData()) as Float32Array;
      const { T, fw, cg, fg } = plan(cw, wstart, durations, speed);
      stats.text += performance.now() - t0;

      t0 = performance.now();
      const noise = gaussian(seed * 1000003 + k)(nSteps * T * D);
      const { latents } = await this.sound.run({
        h, cg: f32(cg, [1, cg.length]), fg: f32(fg, [1, T]), cw: i64(cw), fw: i64(fw),
        noise: f32(noise, [1, nSteps, T, D]) });
      const lat = (await latents.getData()) as Float32Array; // [T, D]
      stats.sound += performance.now() - t0;

      for (const [s, e] of windows(T, k === 0 ? FIRST_WINDOW : WINDOW)) {
        t0 = performance.now();
        const a = Math.max(0, s - CONTEXT), b = Math.min(T, e + CONTEXT), n = b - a;
        const z = new Float32Array(D * n); // [1, D, n]
        for (let f = 0; f < n; f++) for (let d = 0; d < D; d++) z[d * n + f] = lat[(a + f) * D + d];
        const { audio } = await this.decoder.run({ z: f32(z, [1, D, n]) });
        const wav = ((await audio.getData()) as Float32Array).slice((s - a) * hop, (e - a) * hop);
        stats.decode += performance.now() - t0;
        yield wav;
      }
      if (pause) yield new Float32Array(Math.round(pause * RATE));
    }
  }
}
