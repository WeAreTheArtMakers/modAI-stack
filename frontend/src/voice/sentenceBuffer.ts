// Turns streamed RAG tokens into speakable phrases as early as possible, in order.
import { speakable } from "./speechText";

export { speakable } from "./speechText";

const ABBREVIATIONS = new Set(["dr", "prof", "doç", "av", "vb", "vs", "örn", "bkz", "no", "sn", "st", "md", "mad", "tel", "yy", "max", "maks", "min", "yak", "inc", "ltd", "şti", "a.ş", "mr", "ms", "etc", "e.g", "i.e"]);
const FIRST_PHRASE_MIN_CHARS = 28; // the first phrase may end at a comma once it is this long
const FIRST_PHRASE_MIN_WORDS = 4;
const FIRST_PHRASE_MAX_CHARS = 90; // ... and is cut at a word boundary if no punctuation comes
const MAX_PENDING = 200; // later phrases are cut at a clause boundary beyond this
const MIN_WORDS = 2; // shorter fragments ("1.", "Evet.") wait for the next phrase

function isSentenceEnd(text: string, index: number): boolean {
  // `index` is the position of a sentence-ending mark; the next character must be whitespace
  // and must already have arrived, so "3.5" or "v1.2" never split mid-stream.
  const next = text[index + 1];
  if (next === undefined || !/\s/.test(next)) return false;
  if (text[index] !== ".") return true;
  const word = text.slice(0, index).split(/\s/).pop() ?? "";
  if (ABBREVIATIONS.has(word.toLocaleLowerCase("tr").replace(/^[("'“]+/, ""))) return false;
  if (/^\d+$/.test(word)) {
    // "10. madde" is an ordinal; a capital letter after the space starts a new sentence.
    const after = text.slice(index + 1).trimStart();
    return after.length > 0 && /^[\p{Lu}"“(]/u.test(after);
  }
  return true;
}

const wordCount = (text: string) => text.split(/\s+/).filter(Boolean).length;

export class SentenceBuffer {
  private pending = "";
  private held = ""; // a too-short fragment waiting to be joined to the next phrase
  private emitted = 0;

  private take(end: number, out: string[]) {
    const phrase = `${this.held} ${this.pending.slice(0, end)}`.trim();
    this.pending = this.pending.slice(end);
    if (!phrase) return;
    if (wordCount(phrase) < MIN_WORDS) { this.held = phrase; return; }
    this.held = "";
    out.push(phrase);
    this.emitted += 1;
  }

  private clauseCut(limit: number, minimum: number): number {
    const head = this.pending.slice(0, limit);
    const clause = Math.max(head.lastIndexOf(", "), head.lastIndexOf("; "), head.lastIndexOf(": "), head.lastIndexOf(" – "));
    if (clause >= minimum) return clause + 1;
    const space = head.lastIndexOf(" ");
    return space > 0 ? space : -1;
  }

  push(token: string): string[] {
    this.pending += token;
    const out: string[] = [];
    for (let i = 0; i < this.pending.length; i++) {
      const ch = this.pending[i];
      if (ch === "\n" || (/[.!?…]/.test(ch) && isSentenceEnd(this.pending, i))) {
        let end = i + 1;
        while (ch !== "\n" && /["')\]”»]/.test(this.pending[end] ?? "")) end++;
        this.take(end, out);
        i = -1;
        continue;
      }
      // Start speaking before the first sentence ends: cut it at a comma once it is long enough.
      if (this.emitted === 0 && /[,;:]/.test(ch) && /\s/.test(this.pending[i + 1] ?? "")) {
        const head = `${this.held} ${this.pending.slice(0, i + 1)}`.trim();
        if (head.length >= FIRST_PHRASE_MIN_CHARS && wordCount(head) >= FIRST_PHRASE_MIN_WORDS) {
          this.take(i + 1, out);
          i = -1;
        }
      }
    }
    const limit = this.emitted === 0 ? FIRST_PHRASE_MAX_CHARS : MAX_PENDING;
    if (this.pending.length > limit) {
      const cut = this.clauseCut(limit, this.emitted === 0 ? FIRST_PHRASE_MIN_CHARS : 60);
      if (cut > 0) this.take(cut, out);
    }
    return out.map(speakable).filter(Boolean);
  }

  flush(): string[] {
    const rest = speakable(`${this.held} ${this.pending}`);
    this.pending = "";
    this.held = "";
    return rest ? [rest] : [];
  }
}
