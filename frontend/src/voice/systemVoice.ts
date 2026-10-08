// Labeled fallback when neural TTS cannot run: the browser's own Turkish voice.
export interface SystemVoice {
  available(): boolean;
  voiceName(): string | null;
  speak(text: string, onStart: () => void): Promise<void>;
  cancel(): void;
}

export class BrowserSystemVoice implements SystemVoice {
  private turkishVoice(): SpeechSynthesisVoice | null {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    return voices.find((voice) => voice.lang.toLowerCase() === "tr-tr") ?? voices.find((voice) => voice.lang.toLowerCase().startsWith("tr")) ?? null;
  }

  available(): boolean {
    return this.turkishVoice() !== null;
  }

  voiceName(): string | null {
    return this.turkishVoice()?.name ?? null;
  }

  speak(text: string, onStart: () => void): Promise<void> {
    const voice = this.turkishVoice();
    if (!voice) return Promise.reject(new Error("Türkçe sistem sesi bulunamadı."));
    return new Promise((resolve) => {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.onstart = () => onStart();
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve(); // cancellation also lands here
      window.speechSynthesis.speak(utterance);
    });
  }

  cancel() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
  }
}
