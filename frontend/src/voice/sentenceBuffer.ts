// Turns streamed RAG tokens into speakable sentences as early as possible, in order.

const ABBREVIATIONS = new Set(["dr", "prof", "doç", "av", "vb", "vs", "örn", "bkz", "no", "sn", "st", "md", "mad", "tel", "yy", "max", "min", "inc", "ltd", "şti", "a.ş", "mr", "ms", "etc", "e.g", "i.e"]);
const MAX_PENDING = 240;

function isBoundary(text: string, index: number): boolean {
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

export class SentenceBuffer {
  private pending = "";

  push(token: string): string[] {
    this.pending += token;
    const sentences: string[] = [];
    let start = 0;
    for (let i = 0; i < this.pending.length; i++) {
      const ch = this.pending[i];
      const newline = ch === "\n";
      if (newline || (/[.!?…]/.test(ch) && isBoundary(this.pending, i))) {
        let end = i + 1;
        while (!newline && /["')\]”»]/.test(this.pending[end] ?? "")) end++;
        const sentence = this.pending.slice(start, end).trim();
        if (sentence) sentences.push(sentence);
        start = end;
      }
    }
    this.pending = this.pending.slice(start);
    if (this.pending.length > MAX_PENDING) {
      const head = this.pending.slice(0, MAX_PENDING);
      const cut = Math.max(head.lastIndexOf(", "), head.lastIndexOf("; "), head.lastIndexOf(": "));
      const at = cut > 40 ? cut + 1 : head.lastIndexOf(" ");
      if (at > 0) {
        sentences.push(this.pending.slice(0, at).trim());
        this.pending = this.pending.slice(at);
      }
    }
    return sentences.map(speakable).filter(Boolean);
  }

  flush(): string[] {
    const rest = speakable(this.pending);
    this.pending = "";
    return rest ? [rest] : [];
  }
}

/** Removes markdown and citation markup that should be read, not spoken. */
export function speakable(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/https?:\/\/\S+/g, " bağlantı ")
    .replace(/\[(\d+|kaynak[^\]]*)\]/gi, " ")
    .replace(/[*_#>`|~]+/g, " ")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}
