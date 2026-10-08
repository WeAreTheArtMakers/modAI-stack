// Spoken form of an answer sentence. The written answer is never changed; this only removes
// markup and rewrites the few forms that EMA Lightning's own Turkish normalizer reads badly
// (it already reads dates, times, money, percentages and most abbreviations well).

const ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"];
const TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"];
const ORDINAL: Record<string, string> = {
  bir: "birinci", iki: "ikinci", üç: "üçüncü", dört: "dördüncü", beş: "beşinci", altı: "altıncı", yedi: "yedinci",
  sekiz: "sekizinci", dokuz: "dokuzuncu", on: "onuncu", yirmi: "yirminci", otuz: "otuzuncu", kırk: "kırkıncı",
  elli: "ellinci", altmış: "altmışıncı", yetmiş: "yetmişinci", seksen: "sekseninci", doksan: "doksanıncı",
};

/** 1..99 as a Turkish ordinal word ("on ikinci"), or null outside that range. */
export function turkishOrdinal(value: number): string | null {
  if (!Number.isInteger(value) || value < 1 || value > 99) return null;
  const words = [TENS[Math.floor(value / 10)], ONES[value % 10]].filter(Boolean);
  const last = words.pop()!;
  return [...words, ORDINAL[last]].join(" ");
}

// English-origin IT acronyms as Turkish speakers say them; the normalizer would spell them
// with Turkish letter names ("SLA" -> "se le a", "IT" -> "ı te").
const ACRONYMS: Record<string, string> = {
  IT: "ay ti", SLA: "es el ey", HR: "eyç ar", VPN: "vi pi en", SSO: "es es o", MFA: "em ef ey",
  "2FA": "iki adımlı doğrulama", SMS: "es em es", CRM: "si ar em", ERP: "i ar pi", API: "ey pi ay",
  PDF: "pi di ef", ISO: "iso", KPI: "key pi ay",
};
const ACRONYM_PATTERN = new RegExp(`(?<![\\p{L}\\d])(${Object.keys(ACRONYMS).join("|")})(?![\\p{L}\\d])(?:'(?=\\p{L}))?`, "gu");

const ABBREVIATIONS: [RegExp, string][] = [
  [/(?<![\p{L}\d])bkz\./giu, "bakınız"],
  [/(?<![\p{L}\d])örn\./giu, "örneğin"],
  [/(?<![\p{L}\d])maks?\./giu, "en fazla"],
  [/(?<![\p{L}\d])min\.(?=\s*\d)/giu, "en az"],
  [/(?<![\p{L}\d])vs\./gu, "vesaire"],
  [/(?<![\p{L}\d])yak\./giu, "yaklaşık"],
  [/(?<![\p{L}\d])md\.(?=\s*\d)/giu, "madde"],
  [/(?<![\p{L}\d])No[.:](?=\s*\d)/gu, "numara"],
  [/(?<![\p{L}\d])Tel[.:]/gu, "telefon"],
];

const FILE_NAME = /(?<![\p{L}\d/])([\p{L}\d][\p{L}\d_-]*)\.(md|pdf|docx?|txt|xlsx?|csv|pptx?)(?![\p{L}\d])/giu;

function fileNameWords(stem: string): string {
  return stem.replace(/[-_]+/g, " ").replace(/(?<![\p{L}\d])v(\d+)(?![\p{L}\d])/giu, "sürüm $1");
}

function expandAbbreviations(text: string): string {
  return ABBREVIATIONS.reduce((out, [pattern, replacement]) => out.replace(pattern, replacement), text);
}

/** Removes markup and rewrites forms the TTS normalizer would misread; facts are preserved. */
export function speakable(text: string): string {
  return expandAbbreviations(text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\((?:https?:\/\/|\/)[^)]*\)/g, "$1")
    // citation markers and source identifiers: [1], [1, 2], [Kaynak 2], (Kaynak: x.md), 【...】
    .replace(/\[(?:\d+(?:\s*[,–-]\s*\d+)*|(?:kaynak|source|belge|doc)[^\]]*)\]/giu, " ")
    .replace(/\((?:kaynak|kaynaklar|source|sources)\s*:?[^)]*\)/giu, " ")
    .replace(/【[^】]*】/g, " ")
    .replace(/(?:https?:\/\/|www\.)[^\s)]+/g, " bağlantı ")
    .replace(FILE_NAME, (_match, stem: string) => fileNameWords(stem))
    .replace(/(?<![\p{L}\d])doc-(\d+)(?![\p{L}\d])/giu, "belge $1")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/^\s*\|?\s*:?-{3,}.*$/gm, " ")
    .replace(/[*_#>|~]+/g, " "))
    // times: "08.00-17.00" and "saat 9.30" use dots; leading zeros make "09:30'a" unreadable
    .replace(/(?<![\d.])([01]?\d|2[0-3])\.([0-5]\d)\s*[–-]\s*([01]?\d|2[0-3])\.([0-5]\d)(?![\d.])/g, "$1:$2 ile $3:$4")
    .replace(/(?<![\p{L}\d])saat\s+([01]?\d|2[0-3])\.([0-5]\d)(?![\d.])/giu, "saat $1:$2")
    .replace(/(?<![\d:])(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})(?![\d:])/g, "$1 ile $2")
    .replace(/(?<![\d:])0(\d):([0-5]\d)(?![\d:])/g, "$1:$2")
    // numeric ranges ("3-5 iş günü"), but never ISO dates or other dash-joined numbers
    .replace(/(?<![\d.,:-])(\d+(?:[.,]\d+)?)\s*[–-]\s*(\d+(?:[.,]\d+)?)(?![\d.,:-])/g, "$1 ile $2")
    .replace(/(\d)\s*TL'l[iı]k(?![\p{L}])/gu, "$1 liralık")
    .replace(/(?<![\d/])24\/7(?![\d/])/g, "yedi gün yirmi dört saat")
    .replace(/(?<![\p{L}\d])Q([1-4])(?![\p{L}\d])/gu, (_match, quarter: string) => `${turkishOrdinal(Number(quarter))} çeyrek`)
    .replace(/(?<![\p{L}\d])v(\d+(?:\.\d+)*)(?![\p{L}\d])/gu, "sürüm $1")
    // ordinals: "3. kat" -> "üçüncü kat"; a capital letter after the dot ends a sentence instead
    .replace(/(?<![\d.,])(\d{1,2})\.(?=\s+[a-zçğıöşü])/gu, (match, digits: string) => turkishOrdinal(Number(digits)) ?? match)
    .replace(ACRONYM_PATTERN, (_match, acronym: string) => `${ACRONYMS[acronym]} `)
    .replace(/(\p{L})\/(\p{L})/gu, "$1 $2")
    .replace(/\s+([.,;:!?])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}
