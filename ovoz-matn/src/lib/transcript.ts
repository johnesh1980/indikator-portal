/**
 * Real vaqt rejimida kelayotgan tokenlarni (so'z bo'laklarini) til bo'yicha
 * segmentlarga (abzaslarga) yig'uvchi sof mantiq. UI va tarmoqdan mustaqil,
 * shuning uchun Node'da test qilinadi.
 */

export type LangCode = 'uz' | 'ru' | 'en' | string;

export interface Segment {
  id: string;
  /** Aniqlangan til kodi (ISO 639-1), noma'lum bo'lsa undefined */
  lang?: LangCode;
  text: string;
  /** Yozuv boshidan hisoblangan vaqt, millisekundlarda */
  startMs?: number;
}

export interface StreamToken {
  text: string;
  is_final: boolean;
  language?: string;
  start_ms?: number;
  end_ms?: number;
}

/** Soniox maxsus tokenlari: gap tugashi va majburiy yakunlash belgilari. */
const BREAK_TOKENS = new Set(['<end>', '<fin>']);

let idCounter = 0;
const newId = () => `${Date.now().toString(36)}-${(idCounter++).toString(36)}`;

export class TranscriptBuilder {
  private segments: Segment[] = [];
  private pending: StreamToken[] = [];
  private breakNext = false;
  /** Har bir qayta ulanishda (reconnect) vaqtni davom ettirish uchun siljish */
  private offsetMs = 0;

  constructor(initial: Segment[] = []) {
    this.segments = initial.map((s) => ({ ...s }));
  }

  /** Yangi WebSocket sessiyasi boshlanganda vaqt siljishini o'rnatadi. */
  setTimeOffset(ms: number) {
    this.offsetMs = ms;
  }

  /** Bitta server javobidagi tokenlarni qo'llaydi. */
  apply(tokens: StreamToken[]) {
    const nextPending: StreamToken[] = [];
    for (const token of tokens) {
      if (BREAK_TOKENS.has(token.text)) {
        if (token.is_final) this.breakNext = true;
        continue;
      }
      if (token.is_final) this.appendFinal(token);
      else nextPending.push(token);
    }
    // Soniox har javobda yakunlanmagan tokenlarni to'liq qayta yuboradi.
    this.pending = nextPending;
  }

  /** Paragrafni majburan yopish (masalan, foydalanuvchi pauza qilganda). */
  breakParagraph() {
    this.breakNext = true;
  }

  /** Yakunlanmagan tokenlarni tashlab yuboradi (ulanish uzilganda). */
  dropPending() {
    this.pending = [];
  }

  private appendFinal(token: StreamToken) {
    const last = this.segments[this.segments.length - 1];
    const lang = token.language ?? last?.lang;
    const isBlank = token.text.trim().length === 0;
    const langChanged = !!last && !!token.language && !!last.lang && token.language !== last.lang;

    if (!last || ((this.breakNext || langChanged) && !isBlank)) {
      if (isBlank) return;
      this.segments.push({
        id: newId(),
        lang,
        text: token.text.trimStart(),
        startMs: token.start_ms != null ? token.start_ms + this.offsetMs : undefined,
      });
      this.breakNext = false;
      return;
    }
    last.text += token.text;
    if (!last.lang && token.language) last.lang = token.language;
  }

  getSegments(): Segment[] {
    return this.segments;
  }

  /** Ekranda ko'rsatish uchun: yakuniy segmentlar + kulrang (taxminiy) qism. */
  snapshot(): { segments: Segment[]; pendingText: string; pendingLang?: string } {
    const pendingText = this.pending.map((t) => t.text).join('');
    const pendingLang = this.pending.find((t) => t.language)?.language;
    return {
      segments: this.segments.map((s) => ({ ...s })),
      pendingText,
      pendingLang,
    };
  }

  /** To'liq yakuniy matn (tahrirlash va nusxa olish uchun). */
  toPlainText(): string {
    return segmentsToPlainText(this.segments);
  }
}

export function segmentsToPlainText(segments: Segment[]): string {
  return segments
    .map((s) => s.text.trim())
    .filter(Boolean)
    .join('\n\n');
}

export function formatTimestamp(ms?: number): string {
  if (ms == null || ms < 0) return '';
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export const LANGUAGE_LABELS: Record<string, { short: string; name: string; flag: string }> = {
  uz: { short: 'UZ', name: "O'zbekcha", flag: '🇺🇿' },
  ru: { short: 'RU', name: 'Русский', flag: '🇷🇺' },
  en: { short: 'EN', name: 'English', flag: '🇬🇧' },
};

export function langLabel(lang?: string) {
  if (!lang) return { short: '··', name: '—', flag: '🌐' };
  return LANGUAGE_LABELS[lang] ?? { short: lang.toUpperCase(), name: lang, flag: '🌐' };
}

/** Matndagi tillar bo'yicha statistika (Word fayl sarlavhasi uchun). */
export function detectedLanguages(segments: Segment[]): string[] {
  const seen: string[] = [];
  for (const s of segments) if (s.lang && !seen.includes(s.lang)) seen.push(s.lang);
  return seen;
}
