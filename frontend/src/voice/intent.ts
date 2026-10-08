// Deterministic handling of messages that are not document questions, before any retrieval:
// the local generation model otherwise answers "Merhaba" with a summary of whatever document
// was retrieved. Anything that carries other content words is treated as a document question.

export type VoiceIntent = "greeting" | "thanks" | "capability" | "question";

const GREETINGS = [
  "merhaba", "merhabalar", "selam", "selamlar", "günaydın", "iyi günler", "iyi akşamlar", "iyi geceler",
  "hey", "alo", "nasılsın", "nasılsınız", "naber", "hello", "hi",
];
const THANKS = ["teşekkürler", "teşekkür ederim", "çok teşekkürler", "çok teşekkür ederim", "sağ ol", "sağol", "sağ olun", "eyvallah", "thanks", "thank you"];
const FILLERS = new Set(["peki", "tamam", "acaba", "lütfen", "şimdi", "bugün", "ya", "ve", "de", "da"]);
// Words that may appear in "what can you do / how can you help me" with Whisper's spelling.
const CAPABILITY_WORDS = new Set([
  "bana", "benden", "bize", "sen", "siz", "nasıl", "ne", "neler", "nelerde", "hangi", "konularda", "konuda",
  "yardımcı", "olabilirsin", "olabilir", "olabilirsiniz", "misin", "mısın", "yapabilirsin", "yapabilirsiniz",
  "kimsin", "işe", "yararsın", "sorabilirim", "soru", "sorular", "biliyorsun", "mi", "mı", "nedir",
]);
const CAPABILITY_PATTERN = /yardımcı ol|ne(?:ler)? yapabilir|ne işe yarar|kimsin|neler sorabilirim/;

function normalize(text: string): string {
  return text.toLocaleLowerCase("tr").replace(/[^\p{L}\d\s']/gu, " ").replace(/\s+/g, " ").trim();
}

function strip(text: string, phrases: string[]): string {
  let out = ` ${text} `;
  for (const phrase of [...phrases].sort((a, b) => b.length - a.length)) out = out.split(` ${phrase} `).join(" ");
  return out.replace(/\s+/g, " ").trim();
}

export function classifyIntent(text: string): VoiceIntent {
  const normalized = normalize(text);
  if (!normalized) return "question";
  const withoutThanks = strip(normalized, THANKS);
  const rest = strip(withoutThanks, GREETINGS).split(" ").filter((word) => word && !FILLERS.has(word));
  if (!rest.length) return withoutThanks !== normalized ? "thanks" : "greeting";
  if (CAPABILITY_PATTERN.test(rest.join(" ")) && rest.length <= 8) {
    // Tolerate one misrecognized short word ("benden sürü yardımcı olabilirsin").
    const unknown = rest.filter((word) => !CAPABILITY_WORDS.has(word));
    if (unknown.length === 0 || (unknown.length === 1 && unknown[0].length <= 5)) return "capability";
  }
  return "question";
}

export const LOCAL_REPLIES: Record<Exclude<VoiceIntent, "question">, string> = {
  greeting: "Merhaba! Seçtiğiniz bilgi kaynaklarındaki belgeler hakkında soru sorabilirsiniz. Yanıtı belgelere dayanarak verir ve kaynaklarını gösteririm.",
  thanks: "Rica ederim. Başka bir sorunuz varsa dinliyorum.",
  capability: "Seçtiğiniz Knowledge Base'lerdeki belgelerden yanıt verebilirim. Politikalar, süreler ya da onay adımları gibi konularda Türkçe soru sorun; yanıtı kaynaklarıyla birlikte gösterir ve sesli okurum.",
};

// Words that are also Turkish ("on", "at", "it", "an", "as", "is", "can") are left out on purpose.
const ENGLISH = new Set("the and of to in for with are was were you your this that be by or if will must should from not all any after before into when which there their these those have has".split(" "));
const TURKISH = new Set("ve bir bu için ile da de mi mı olarak gibi daha çok var yok olan veya ise göre sonra önce kadar en ancak değil içinde ayrıca şu tüm her".split(" "));

/** Rough sentence language for the Turkish-only voice: "en" only with clear English evidence. */
export function sentenceLanguage(text: string): "tr" | "en" | "unknown" {
  const words = text.toLocaleLowerCase("tr").match(/[\p{L}']+/gu) ?? [];
  if (words.length < 4) return "unknown";
  const english = words.filter((word) => ENGLISH.has(word)).length;
  const turkish = words.filter((word) => TURKISH.has(word) || /[çğıöşü]/.test(word)).length;
  if (english >= 3 && english > 2 * turkish) return "en";
  if (turkish > 0 && turkish >= english) return "tr";
  return "unknown";
}
