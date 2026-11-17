import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, mkdirSync } from 'node:fs';
import { TranscriptBuilder, formatTimestamp, segmentsToPlainText, detectedLanguages } from '../src/lib/transcript';
import { SonioxSession, buildSonioxRequest, isFatalCode } from '../src/lib/soniox';
import { buildDocxBase64, safeFileName } from '../src/lib/docx';

test('tokenlar til bo‘yicha segmentlarga ajraladi, yakunlanmaganlar alohida', () => {
  const b = new TranscriptBuilder();
  b.apply([
    { text: 'Assalomu', is_final: true, language: 'uz', start_ms: 0 },
    { text: ' alaykum', is_final: true, language: 'uz' },
    { text: ' hurmatli', is_final: false, language: 'uz' },
  ]);
  let snap = b.snapshot();
  assert.equal(snap.segments.length, 1);
  assert.equal(snap.segments[0].text, 'Assalomu alaykum');
  assert.equal(snap.pendingText, ' hurmatli');

  b.apply([
    { text: ' hurmatli', is_final: true, language: 'uz' },
    { text: ' talabalar.', is_final: true, language: 'uz' },
    { text: ' Сегодня', is_final: true, language: 'ru', start_ms: 3200 },
    { text: ' мы', is_final: true, language: 'ru' },
    { text: ' Today', is_final: true, language: 'en', start_ms: 5000 },
  ]);
  snap = b.snapshot();
  assert.equal(snap.pendingText, '');
  assert.deepEqual(snap.segments.map((s) => [s.lang, s.text]), [
    ['uz', 'Assalomu alaykum hurmatli talabalar.'],
    ['ru', 'Сегодня мы'],
    ['en', 'Today'],
  ]);
  assert.equal(snap.segments[1].startMs, 3200);
  assert.deepEqual(detectedLanguages(snap.segments), ['uz', 'ru', 'en']);
});

test('<end> tokeni yangi abzas boshlaydi va matnga kirmaydi', () => {
  const b = new TranscriptBuilder();
  b.apply([{ text: 'Birinchi gap.', is_final: true, language: 'uz' }, { text: '<end>', is_final: true }]);
  b.apply([{ text: ' Ikkinchi gap.', is_final: true, language: 'uz' }]);
  const segs = b.getSegments();
  assert.equal(segs.length, 2);
  assert.equal(segs[1].text, 'Ikkinchi gap.');
  assert.equal(segmentsToPlainText(segs), 'Birinchi gap.\n\nIkkinchi gap.');
});

test('qayta ulanishda vaqt siljishi qo‘llanadi', () => {
  const b = new TranscriptBuilder();
  b.setTimeOffset(60_000);
  b.apply([{ text: 'Davom', is_final: true, language: 'uz', start_ms: 500 }]);
  assert.equal(b.getSegments()[0].startMs, 60_500);
  assert.equal(formatTimestamp(60_500), '01:00');
  assert.equal(formatTimestamp(3_725_000), '1:02:05');
});

test('Soniox so‘rovi to‘g‘ri tuziladi', () => {
  const req = buildSonioxRequest({ apiKey: 'k', sampleRate: 16000, contextTerms: [' KPI ', ''] });
  assert.equal(req.audio_format, 'pcm_s16le');
  assert.equal(req.enable_language_identification, true);
  assert.deepEqual(req.language_hints, ['uz', 'ru', 'en']);
  assert.deepEqual(req.context, { terms: ['KPI'] });
  assert.ok(isFatalCode(401) && !isFatalCode(503));
});

class FakeWS {
  readyState = 0;
  sent: unknown[] = [];
  onopen: any = null; onmessage: any = null; onerror: any = null; onclose: any = null;
  send(d: unknown) { this.sent.push(d); }
  close() { this.readyState = 3; this.onclose?.({}); }
  open() { this.readyState = 1; this.onopen?.({}); }
  msg(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
}

test('SonioxSession: konfiguratsiya, bufer, tokenlar, yakunlash', async () => {
  const ws = new FakeWS();
  const got: any[] = [];
  let closed: boolean | null = null;
  const s = new SonioxSession(
    { apiKey: 'KEY', sampleRate: 16000 },
    { onTokens: (t) => got.push(...t), onError: () => assert.fail('xato kutilmagan'), onClose: (e) => (closed = e) },
    () => ws as any,
  );
  s.start();
  s.sendAudio(new ArrayBuffer(320)); // ulanishdan oldin — buferga
  ws.open();
  assert.equal(JSON.parse(ws.sent[0] as string).api_key, 'KEY');
  assert.ok(ws.sent[1] instanceof ArrayBuffer, 'buferdagi audio ochilganda yuboriladi');
  s.sendAudio(new ArrayBuffer(320));
  assert.equal(ws.sent.length, 3);
  ws.msg({ tokens: [{ text: 'Salom', is_final: true, language: 'uz' }] });
  assert.equal(got[0].text, 'Salom');
  s.stop();
  assert.equal(ws.sent[ws.sent.length - 1], '', 'stop bo‘sh freym yuboradi');
  ws.msg({ tokens: [], finished: true });
  assert.equal(closed, true);
});

test('SonioxSession: 401 xatosi halokatli deb belgilanadi', () => {
  const ws = new FakeWS();
  let fatal = false; let msg = '';
  const s = new SonioxSession({ apiKey: 'bad', sampleRate: 16000 },
    { onTokens: () => {}, onError: (m, f) => { msg = m; fatal = f; }, onClose: () => {} }, () => ws as any);
  s.start(); ws.open();
  ws.msg({ error_code: 401, error_message: 'Invalid API key' });
  assert.ok(fatal);
  assert.match(msg, /API kalit/);
  s.abort();
});

test('Word (.docx) fayl yaratiladi', async () => {
  const b = new TranscriptBuilder();
  b.apply([
    { text: 'Assalomu alaykum, bugungi ma’ruza mavzusi — sun’iy intellekt.', is_final: true, language: 'uz', start_ms: 0 },
    { text: '<end>', is_final: true },
    { text: 'Искусственный интеллект меняет мир.', is_final: true, language: 'ru', start_ms: 4100 },
    { text: ' Machine learning is a subset of AI.', is_final: true, language: 'en', start_ms: 9000 },
  ]);
  const b64 = await buildDocxBase64(b.getSegments(), {
    title: "Ma'ruza: Sun'iy intellekt", createdAt: Date.UTC(2026, 10, 17, 9, 30), durationMs: 754_000,
    includeTimestamps: true, includeLanguageTags: true,
  });
  const buf = Buffer.from(b64, 'base64');
  assert.equal(buf.subarray(0, 2).toString(), 'PK', 'docx — zip arxiv');
  mkdirSync('tests/out', { recursive: true });
  writeFileSync('tests/out/namuna.docx', buf);
  assert.equal(safeFileName('A/B: test?', Date.UTC(2026, 0, 2, 3, 4)).endsWith('.docx'), true);
  assert.ok(!safeFileName('A/B: test?', 0).includes('/'));
});
