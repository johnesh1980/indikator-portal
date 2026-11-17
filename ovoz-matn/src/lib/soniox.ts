/**
 * Soniox real-time WebSocket klienti.
 * Protokol: ulanish ochilgach JSON konfiguratsiya yuboriladi, so'ng binar
 * PCM (s16le) audio bo'laklari, oxirida bo'sh freym ("") — server qolgan
 * tokenlarni yakunlab `finished: true` qaytaradi.
 */
import type { StreamToken } from './transcript';

export const SONIOX_WS_URL = 'wss://stt-rt.soniox.com/transcribe-websocket';
export const DEFAULT_SONIOX_MODEL = 'stt-rt-v4';

export interface SonioxConfig {
  apiKey: string;
  model?: string;
  sampleRate: number;
  /** Kutilayotgan tillar (aniqlashni yaxshilaydi) */
  languageHints?: string[];
  /** Mavzuga oid atamalar (ism, termin) — aniqlikni oshiradi */
  contextTerms?: string[];
  enableDiarization?: boolean;
}

export interface SonioxResponse {
  tokens?: StreamToken[];
  finished?: boolean;
  error_code?: number;
  error_message?: string;
}

export interface SonioxCallbacks {
  onTokens: (tokens: StreamToken[]) => void;
  onError: (message: string, fatal: boolean) => void;
  /** Ulanish yopildi. `expected` — biz o'zimiz to'xtatganmizmi. */
  onClose: (expected: boolean) => void;
  onOpen?: () => void;
}

type WSLike = {
  readyState: number;
  send(data: string | ArrayBuffer | ArrayBufferView): void;
  close(code?: number, reason?: string): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onclose: ((ev: { code?: number; reason?: string }) => void) | null;
};

export type WebSocketFactory = (url: string) => WSLike;

const OPEN = 1;
const KEEPALIVE_MS = 10_000;
/** Ulanish ochilguncha audio buferi chegarasi (~30 s @16 kHz) */
const MAX_QUEUE_BYTES = 16000 * 2 * 30;

export function buildSonioxRequest(cfg: SonioxConfig) {
  const req: Record<string, unknown> = {
    api_key: cfg.apiKey,
    model: cfg.model?.trim() || DEFAULT_SONIOX_MODEL,
    audio_format: 'pcm_s16le',
    sample_rate: cfg.sampleRate,
    num_channels: 1,
    language_hints: cfg.languageHints?.length ? cfg.languageHints : ['uz', 'ru', 'en'],
    enable_language_identification: true,
    enable_endpoint_detection: true,
  };
  if (cfg.enableDiarization) req.enable_speaker_diarization = true;
  const terms = (cfg.contextTerms ?? []).map((t) => t.trim()).filter(Boolean);
  if (terms.length) req.context = { terms };
  return req;
}

export function humanizeSonioxError(code?: number, message?: string): string {
  switch (code) {
    case 401:
      return "API kalit noto'g'ri yoki muddati o'tgan. Sozlamalarni tekshiring.";
    case 402:
      return "Soniox hisobida mablag' tugagan.";
    case 429:
      return "So'rovlar chegarasidan oshdi. Birozdan so'ng urinib ko'ring.";
    case 400:
      return `Noto'g'ri so'rov: ${message ?? ''}`.trim();
    case 408:
      return "Server audio kutib vaqt tugadi (408).";
    case 503:
      return 'Xizmat vaqtincha ishlamayapti (503).';
    default:
      return message ? `Server xatosi (${code ?? '?'}): ${message}` : `Server xatosi (${code ?? '?'})`;
  }
}

/** Qayta urinib bo'lmaydigan xatolar (kalit noto'g'ri, mablag' yo'q, so'rov xato). */
export function isFatalCode(code?: number) {
  return code === 400 || code === 401 || code === 402 || code === 403;
}

export class SonioxSession {
  private ws: WSLike | null = null;
  private queue: ArrayBuffer[] = [];
  private queuedBytes = 0;
  private stopping = false;
  private closedNotified = false;
  private keepaliveTimer: ReturnType<typeof setInterval> | null = null;
  private lastSendAt = 0;

  constructor(
    private cfg: SonioxConfig,
    private cb: SonioxCallbacks,
    private factory: WebSocketFactory = (url) => new WebSocket(url) as unknown as WSLike,
  ) {}

  start() {
    const ws = this.factory(SONIOX_WS_URL);
    this.ws = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify(buildSonioxRequest(this.cfg)));
      for (const chunk of this.queue) ws.send(chunk);
      this.queue = [];
      this.queuedBytes = 0;
      this.lastSendAt = Date.now();
      this.keepaliveTimer = setInterval(() => {
        // Pauza paytida server ulanishni yopmasligi uchun
        if (ws.readyState === OPEN && Date.now() - this.lastSendAt > KEEPALIVE_MS - 500) {
          ws.send('{"type":"keepalive"}');
          this.lastSendAt = Date.now();
        }
      }, KEEPALIVE_MS);
      this.cb.onOpen?.();
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      let res: SonioxResponse;
      try {
        res = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (res.error_code != null || res.error_message != null) {
        this.cb.onError(humanizeSonioxError(res.error_code, res.error_message), isFatalCode(res.error_code));
        return;
      }
      if (res.tokens?.length) this.cb.onTokens(res.tokens);
      if (res.finished) this.close(true);
    };
    ws.onerror = () => {
      if (!this.stopping) this.cb.onError("Internet ulanishida xato. Qayta ulanilmoqda…", false);
    };
    ws.onclose = () => this.notifyClosed(this.stopping);
  }

  /** PCM s16le audio bo'lagini yuboradi. */
  sendAudio(chunk: ArrayBuffer) {
    if (this.stopping) return;
    const ws = this.ws;
    if (ws && ws.readyState === OPEN) {
      ws.send(chunk);
      this.lastSendAt = Date.now();
    } else if (this.queuedBytes + chunk.byteLength <= MAX_QUEUE_BYTES) {
      this.queue.push(chunk);
      this.queuedBytes += chunk.byteLength;
    }
  }

  /** Hozirgacha aytilganlarni darhol yakunlash (pauza tugmasi uchun). */
  finalize() {
    if (this.ws?.readyState === OPEN) this.ws.send('{"type":"finalize"}');
  }

  /** Yumshoq to'xtatish: server qolgan tokenlarni yakunlaydi. */
  stop() {
    if (this.stopping) return;
    this.stopping = true;
    const ws = this.ws;
    if (ws && ws.readyState === OPEN) {
      ws.send('');
      // Server javob bermasa ham 5 soniyadan so'ng yopamiz
      setTimeout(() => this.close(true), 5000);
    } else {
      this.close(true);
    }
  }

  /** Darhol bekor qilish. */
  abort() {
    this.stopping = true;
    this.close(true);
  }

  private close(expected: boolean) {
    if (this.keepaliveTimer) clearInterval(this.keepaliveTimer);
    this.keepaliveTimer = null;
    try {
      this.ws?.close();
    } catch {
      /* e'tiborsiz */
    }
    this.notifyClosed(expected);
  }

  private notifyClosed(expected: boolean) {
    if (this.closedNotified) return;
    this.closedNotified = true;
    if (this.keepaliveTimer) clearInterval(this.keepaliveTimer);
    this.keepaliveTimer = null;
    this.cb.onClose(expected);
  }
}
