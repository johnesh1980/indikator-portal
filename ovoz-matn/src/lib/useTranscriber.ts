/**
 * Ovozni real vaqtda matnga aylantiruvchi asosiy hook.
 *
 *  - "cloud" rejimi: mikrofondan 16 kHz PCM olinadi va Soniox'ga uzatiladi.
 *    Har bir so'z uchun til (uz/ru/en) avtomatik aniqlanadi.
 *  - "device" rejimi: telefonning o'z nutq tanish tizimi (internet talab
 *    qilinishi mumkin), til qo'lda tanlanadi.
 */
import { AudioStudioModule, useAudioRecorder, type AudioDataEvent } from '@siteed/audio-studio';
import { toByteArray } from 'base64-js';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
import { useCallback, useEffect, useRef, useState } from 'react';
import { SonioxSession } from './soniox';
import type { Settings } from './storage';
import { TranscriptBuilder, type Segment } from './transcript';

export type RecState = 'idle' | 'connecting' | 'recording' | 'paused' | 'stopping';

const SAMPLE_RATE = 16000;
const BYTES_PER_MS = (SAMPLE_RATE * 2) / 1000;
const KEEP_AWAKE_TAG = 'ovoz-matn-recording';
const MAX_RECONNECTS = 20;

export interface TranscriberView {
  segments: Segment[];
  pendingText: string;
  pendingLang?: string;
}

export function useTranscriber(settings: Settings) {
  const recorder = useAudioRecorder();
  const [state, setState] = useState<RecState>('idle');
  const [view, setView] = useState<TranscriberView>({ segments: [], pendingText: '' });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  const builder = useRef(new TranscriptBuilder());
  const session = useRef<SonioxSession | null>(null);
  const engineRef = useRef(settings.engine);
  const stateRef = useRef<RecState>('idle');
  const bytesSent = useRef(0);
  const baseOffsetMs = useRef(0);
  const reconnects = useRef(0);
  const clock = useRef({ startedAt: 0, accumulated: 0 });
  const stopResolver = useRef<(() => void) | null>(null);

  const setRecState = (s: RecState) => {
    stateRef.current = s;
    setState(s);
  };

  // UI'ni tez-tez, lekin me'yorida yangilash
  const renderScheduled = useRef(false);
  const refresh = useCallback(() => {
    if (renderScheduled.current) return;
    renderScheduled.current = true;
    requestAnimationFrame(() => {
      renderScheduled.current = false;
      setView(builder.current.snapshot());
    });
  }, []);

  // Taymer
  useEffect(() => {
    if (state !== 'recording') return;
    const t = setInterval(() => {
      const c = clock.current;
      setElapsedMs(c.accumulated + (Date.now() - c.startedAt));
    }, 250);
    return () => clearInterval(t);
  }, [state]);

  const pauseClock = () => {
    const c = clock.current;
    if (c.startedAt) c.accumulated += Date.now() - c.startedAt;
    c.startedAt = 0;
    setElapsedMs(c.accumulated);
  };
  const resumeClock = () => {
    clock.current.startedAt = Date.now();
  };

  // ---------------- Soniox (bulut) ----------------
  const openCloudSession = useCallback(() => {
    builder.current.setTimeOffset(baseOffsetMs.current + Math.round(bytesSent.current / BYTES_PER_MS));
    const s = new SonioxSession(
      {
        apiKey: settings.sonioxApiKey.trim(),
        model: settings.sonioxModel,
        sampleRate: SAMPLE_RATE,
        languageHints: settings.languageHints,
        contextTerms: settings.contextTerms.split(/[,\n]/),
      },
      {
        onOpen: () => {
          reconnects.current = 0;
          setNotice(null);
          if (stateRef.current === 'connecting') setRecState('recording');
        },
        onTokens: (tokens) => {
          builder.current.apply(tokens);
          refresh();
        },
        onError: (msg, fatal) => {
          if (fatal) {
            setError(msg);
            void stopInternal(false);
          } else {
            setNotice(msg);
          }
        },
        onClose: (expected) => {
          if (session.current !== s) return;
          if (expected || stateRef.current === 'stopping' || stateRef.current === 'idle') {
            session.current = null;
            stopResolver.current?.();
            return;
          }
          // Kutilmagan uzilish — matn yo'qolmasligi uchun qayta ulanamiz
          builder.current.dropPending();
          builder.current.breakParagraph();
          refresh();
          if (reconnects.current++ >= MAX_RECONNECTS) {
            setError("Server bilan aloqa tiklanmadi. Internetni tekshiring.");
            void stopInternal(false);
            return;
          }
          setNotice('Aloqa uzildi, qayta ulanilmoqda…');
          setTimeout(() => {
            if (stateRef.current === 'recording' || stateRef.current === 'paused') openCloudSession();
          }, Math.min(1000 * reconnects.current, 5000));
        },
      },
    );
    session.current = s;
    s.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, refresh]);

  const onAudioStream = useCallback(async (ev: AudioDataEvent) => {
    let bytes: Uint8Array;
    if (typeof ev.data === 'string') {
      if (!ev.data) return;
      bytes = toByteArray(ev.data); // native: base64 PCM16
    } else {
      // web: Float32Array yoki Int16Array
      let pcm: Int16Array;
      if (ev.data instanceof Int16Array) pcm = ev.data;
      else {
        pcm = new Int16Array(ev.data.length);
        for (let i = 0; i < ev.data.length; i++) pcm[i] = Math.max(-1, Math.min(1, ev.data[i])) * 0x7fff;
      }
      bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
    }
    bytesSent.current += bytes.byteLength;
    session.current?.sendAudio(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer);
  }, []);

  // ---------------- Qurilma (offline/native) ----------------
  const deviceLangShort = settings.deviceLang.slice(0, 2);
  useSpeechRecognitionEvent('result', (ev) => {
    if (engineRef.current !== 'device' || stateRef.current === 'idle') return;
    const text = ev.results[0]?.transcript ?? '';
    if (!text) return;
    builder.current.apply([{ text: (ev.isFinal ? ' ' : '') + text, is_final: ev.isFinal, language: deviceLangShort }]);
    refresh();
  });
  useSpeechRecognitionEvent('error', (ev) => {
    if (engineRef.current !== 'device') return;
    if (ev.error === 'no-speech' || ev.error === 'speech-timeout' || ev.error === 'aborted') return;
    if (ev.error === 'language-not-supported') {
      setError("Bu til qurilmada qo'llab-quvvatlanmaydi. Bulut rejimini tanlang.");
    } else {
      setError(`Nutq tanish xatosi: ${ev.message || ev.error}`);
    }
    void stopInternal(false);
  });
  useSpeechRecognitionEvent('end', () => {
    if (engineRef.current !== 'device') return;
    // Android ba'zan uzun nutqda to'xtaydi — yozish davom etayotgan bo'lsa qayta ishga tushiramiz
    if (stateRef.current === 'recording') {
      builder.current.breakParagraph();
      startDevice();
    } else if (stateRef.current === 'stopping') {
      stopResolver.current?.();
    }
  });

  const startDevice = useCallback(() => {
    ExpoSpeechRecognitionModule.start({
      lang: settings.deviceLang,
      interimResults: true,
      continuous: true,
      addsPunctuation: true,
      requiresOnDeviceRecognition: false,
      androidIntentOptions: { EXTRA_LANGUAGE_MODEL: 'free_form' },
    });
  }, [settings.deviceLang]);

  // ---------------- Umumiy boshqaruv ----------------
  const start = useCallback(
    async (initial: Segment[] = [], offsetMs = 0) => {
      if (stateRef.current !== 'idle') return;
      setError(null);
      setNotice(null);
      engineRef.current = settings.engine;

      if (settings.engine === 'cloud' && !settings.sonioxApiKey.trim()) {
        setError("Avval Sozlamalarda Soniox API kalitini kiriting (yoki Qurilma rejimini tanlang).");
        return;
      }

      builder.current = new TranscriptBuilder(initial);
      setView(builder.current.snapshot());
      bytesSent.current = 0;
      baseOffsetMs.current = offsetMs;
      reconnects.current = 0;
      clock.current = { startedAt: Date.now(), accumulated: 0 };
      setElapsedMs(0);

      try {
        if (settings.engine === 'cloud') {
          const perm = await AudioStudioModule.requestPermissionsAsync();
          if (!perm.granted) {
            setError('Mikrofonga ruxsat berilmadi.');
            return;
          }
          setRecState('connecting');
          openCloudSession();
          await recorder.startRecording({
            sampleRate: SAMPLE_RATE,
            channels: 1,
            encoding: 'pcm_16bit',
            interval: 100,
            keepAwake: true,
            showNotification: true,
            notification: { title: 'Ovoz → Matn', text: 'Nutq matnga aylantirilmoqda…' },
            output: { primary: { enabled: false } },
            autoResumeAfterInterruption: true,
            onAudioStream,
          });
        } else {
          const perm = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
          if (!perm.granted) {
            setError('Mikrofon va nutq tanishga ruxsat berilmadi.');
            return;
          }
          setRecState('recording');
          startDevice();
        }
        await activateKeepAwakeAsync(KEEP_AWAKE_TAG).catch(() => {});
      } catch (e) {
        setError(`Yozishni boshlab bo'lmadi: ${(e as Error).message}`);
        session.current?.abort();
        session.current = null;
        setRecState('idle');
      }
    },
    [settings, openCloudSession, onAudioStream, recorder, startDevice],
  );

  const pause = useCallback(async () => {
    if (stateRef.current !== 'recording') return;
    pauseClock();
    if (engineRef.current === 'cloud') {
      await recorder.pauseRecording();
      session.current?.finalize();
    } else {
      setRecState('paused');
      ExpoSpeechRecognitionModule.stop();
    }
    builder.current.breakParagraph();
    setRecState('paused');
  }, [recorder]);

  const resume = useCallback(async () => {
    if (stateRef.current !== 'paused') return;
    resumeClock();
    setRecState('recording');
    if (engineRef.current === 'cloud') {
      if (!session.current) openCloudSession();
      await recorder.resumeRecording();
    } else {
      startDevice();
    }
  }, [recorder, openCloudSession, startDevice]);

  /** To'xtatadi va yakuniy segmentlarni qaytaradi. */
  const stopInternal = useCallback(
    async (graceful: boolean): Promise<Segment[]> => {
      const prev = stateRef.current;
      if (prev === 'idle' || prev === 'stopping') return builder.current.getSegments();
      if (prev === 'recording') pauseClock();
      setRecState('stopping');
      const done = new Promise<void>((resolve) => {
        stopResolver.current = resolve;
        setTimeout(resolve, 6000);
      });

      if (engineRef.current === 'cloud') {
        try {
          if (recorder.isRecording || recorder.isPaused) await recorder.stopRecording();
        } catch {
          /* e'tiborsiz */
        }
        if (session.current) {
          if (graceful) session.current.stop();
          else session.current.abort();
          await done;
        }
      } else {
        if (prev === 'recording') {
          ExpoSpeechRecognitionModule.stop();
          await done;
        }
      }
      stopResolver.current = null;
      session.current = null;
      Promise.resolve(deactivateKeepAwake(KEEP_AWAKE_TAG)).catch(() => {});
      setView(builder.current.snapshot());
      setRecState('idle');
      return builder.current.getSegments().map((s) => ({ ...s }));
    },
    [recorder],
  );

  const stop = useCallback(() => stopInternal(true), [stopInternal]);

  const reset = useCallback(() => {
    builder.current = new TranscriptBuilder();
    setView(builder.current.snapshot());
    setElapsedMs(0);
    setError(null);
    setNotice(null);
  }, []);

  // Ekrandan chiqib ketilsa resurslarni bo'shatish
  useEffect(
    () => () => {
      session.current?.abort();
      try {
        ExpoSpeechRecognitionModule.abort();
      } catch {
        /* e'tiborsiz */
      }
    },
    [],
  );

  return { state, view, error, notice, elapsedMs, start, pause, resume, stop, reset, dismissError: () => setError(null) };
}
