import * as Clipboard from 'expo-clipboard';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import TranscriptView from '../components/TranscriptView';
import { saveDocxToFolder, shareDocx } from '../lib/exportFile';
import { saveSession, type SessionData, type Settings } from '../lib/storage';
import { detectedLanguages, formatTimestamp, segmentsToPlainText, type Segment } from '../lib/transcript';
import { useTranscriber } from '../lib/useTranscriber';
import { colors } from '../theme';

interface Props {
  settings: Settings;
  /** Tarixdan ochilgan yozuv */
  opened: SessionData | null;
  onOpenSettings: () => void;
  onOpenHistory: () => void;
  onConsumeOpened: () => void;
}

const newSessionId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const defaultTitle = (ts: number) => {
  const d = new Date(ts);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `Yozuv ${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

export default function RecorderScreen({ settings, opened, onOpenSettings, onOpenHistory, onConsumeOpened }: Props) {
  const tr = useTranscriber(settings);
  const [doc, setDoc] = useState(() => {
    const now = Date.now();
    return { id: newSessionId(), title: defaultTitle(now), createdAt: now, baseDurationMs: 0 };
  });
  /** Yozuvdan keyin (yoki tarixdan ochilganda) tahrirlanadigan segmentlar */
  const [segments, setSegments] = useState<Segment[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<Segment | null>(null);
  const [editText, setEditText] = useState('');
  const [titleEdit, setTitleEdit] = useState(false);

  const isLive = tr.state !== 'idle';
  const shown = isLive ? tr.view.segments : segments;
  const totalMs = doc.baseDurationMs + (isLive ? tr.elapsedMs : 0);

  // Tarixdan ochilgan yozuvni yuklash
  useEffect(() => {
    if (!opened || isLive) return;
    setDoc({ id: opened.id, title: opened.title, createdAt: opened.createdAt, baseDurationMs: opened.durationMs });
    setSegments(opened.segments);
    tr.reset();
    onConsumeOpened();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const persist = async (segs: Segment[], durationMs: number, title = doc.title) => {
    if (!segs.some((s) => s.text.trim())) return;
    const text = segmentsToPlainText(segs);
    await saveSession({
      id: doc.id,
      title,
      createdAt: doc.createdAt,
      durationMs,
      preview: text.slice(0, 160),
      langs: detectedLanguages(segs),
      segments: segs,
    });
  };

  const onRecordPress = async () => {
    if (tr.state === 'idle') {
      // Mavjud matn bo'lsa — davom ettiramiz (yangi bo'laklar oxiriga qo'shiladi)
      await tr.start(segments, doc.baseDurationMs);
    } else if (tr.state === 'recording') {
      await tr.pause();
    } else if (tr.state === 'paused') {
      await tr.resume();
    }
  };

  const onStop = async () => {
    const elapsed = tr.elapsedMs;
    const final = await tr.stop();
    const duration = doc.baseDurationMs + elapsed;
    setSegments(final);
    setDoc((d) => ({ ...d, baseDurationMs: duration }));
    await persist(final, duration).catch(() => {});
  };

  const startNew = () => {
    const go = () => {
      const now = Date.now();
      setDoc({ id: newSessionId(), title: defaultTitle(now), createdAt: now, baseDurationMs: 0 });
      setSegments([]);
      tr.reset();
    };
    if (segments.length) {
      Alert.alert('Yangi yozuv', "Joriy matn tarixda saqlangan. Yangi yozuv boshlansinmi?", [
        { text: 'Bekor', style: 'cancel' },
        { text: 'Ha', onPress: go },
      ]);
    } else go();
  };

  const docxOpts = () => ({
    title: doc.title,
    createdAt: doc.createdAt,
    durationMs: doc.baseDurationMs,
    includeTimestamps: settings.includeTimestamps,
    includeLanguageTags: settings.includeLanguageTags,
  });

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      Alert.alert('Xatolik', (e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onSaveWord = () =>
    run('Word fayl tayyorlanmoqda…', async () => {
      const name = await saveDocxToFolder(segments, docxOpts());
      if (name) Alert.alert('Saqlandi ✅', `${name} fayli tanlangan papkaga saqlandi.`);
    });

  const onShareWord = () => run('Word fayl tayyorlanmoqda…', () => shareDocx(segments, docxOpts()));

  const onCopy = async () => {
    await Clipboard.setStringAsync(segmentsToPlainText(segments));
    Alert.alert('Nusxa olindi', "Matn bufer xotiraga ko'chirildi.");
  };

  const openEdit = (seg: Segment) => {
    if (isLive) return;
    setEditing(seg);
    setEditText(seg.text.trim());
  };

  const saveEdit = async () => {
    if (!editing) return;
    const next = segments
      .map((s) => (s.id === editing.id ? { ...s, text: editText } : s))
      .filter((s) => s.text.trim());
    setSegments(next);
    setEditing(null);
    await persist(next, doc.baseDurationMs).catch(() => {});
  };

  const hasText = segments.some((s) => s.text.trim());
  const titleRef = useRef(doc.title);
  titleRef.current = doc.title;

  const statusText =
    tr.state === 'connecting'
      ? 'Ulanmoqda…'
      : tr.state === 'recording'
        ? settings.engine === 'cloud'
          ? 'Tinglanmoqda · til avtomatik aniqlanadi'
          : `Tinglanmoqda · ${settings.deviceLang}`
        : tr.state === 'paused'
          ? 'Pauza'
          : tr.state === 'stopping'
            ? 'Yakunlanmoqda…'
            : settings.engine === 'cloud'
              ? "☁️ Bulut · O'zbek / Русский / English"
              : `📱 Qurilma · ${settings.deviceLang}`;

  return (
    <View style={styles.root}>
      {/* Sarlavha */}
      <View style={styles.header}>
        <Pressable onPress={onOpenHistory} hitSlop={10} disabled={isLive}>
          <Text style={[styles.icon, isLive && styles.disabled]}>☰</Text>
        </Pressable>
        <Pressable style={{ flex: 1 }} onPress={() => !isLive && setTitleEdit(true)}>
          <Text style={styles.title} numberOfLines={1}>
            {doc.title}
          </Text>
          <Text style={styles.status} numberOfLines={1}>
            {statusText}
          </Text>
        </Pressable>
        <Pressable onPress={onOpenSettings} hitSlop={10} disabled={isLive}>
          <Text style={[styles.icon, isLive && styles.disabled]}>⚙︎</Text>
        </Pressable>
      </View>

      {tr.error && (
        <Pressable style={[styles.banner, { backgroundColor: '#4A1E26' }]} onPress={tr.dismissError}>
          <Text style={styles.bannerText}>⚠️ {tr.error}</Text>
        </Pressable>
      )}
      {!tr.error && tr.notice && (
        <View style={[styles.banner, { backgroundColor: '#4A3A15' }]}>
          <Text style={styles.bannerText}>{tr.notice}</Text>
        </View>
      )}

      <TranscriptView
        segments={shown}
        pendingText={isLive ? tr.view.pendingText : ''}
        pendingLang={tr.view.pendingLang}
        live={isLive}
        showTimestamps={settings.includeTimestamps}
        onEditSegment={openEdit}
        placeholder={
          "Mikrofon tugmasini bosing va gapiring.\n\nMa'ruza, yig'ilish yoki suhbat matni shu yerda real vaqtda paydo bo'ladi.\n\nO'zbek · Русский · English"
        }
      />

      {/* Boshqaruv paneli */}
      <View style={styles.footer}>
        <Text style={styles.timer}>{formatTimestamp(totalMs) || '00:00'}</Text>
        <View style={styles.controls}>
          <View style={styles.side}>
            {isLive ? (
              <RoundBtn label="■" sub="To'xtatish" onPress={onStop} disabled={tr.state === 'connecting' || tr.state === 'stopping'} />
            ) : hasText ? (
              <RoundBtn label="＋" sub="Yangi" onPress={startNew} />
            ) : null}
          </View>
          <Pressable
            onPress={onRecordPress}
            disabled={tr.state === 'connecting' || tr.state === 'stopping'}
            style={[styles.recBtn, tr.state === 'recording' && styles.recBtnActive]}
          >
            {tr.state === 'connecting' || tr.state === 'stopping' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.recIcon}>{tr.state === 'recording' ? '❚❚' : tr.state === 'paused' ? '▶' : '🎙'}</Text>
            )}
          </Pressable>
          <View style={styles.side}>
            {!isLive && hasText ? <RoundBtn label="⧉" sub="Nusxa" onPress={onCopy} /> : null}
          </View>
        </View>
        {!isLive && hasText && (
          <View style={styles.exportRow}>
            <Pressable style={[styles.exportBtn, { backgroundColor: colors.accent }]} onPress={onSaveWord}>
              <Text style={styles.exportText}>💾 Word saqlash</Text>
            </Pressable>
            <Pressable style={[styles.exportBtn, { backgroundColor: colors.surface2 }]} onPress={onShareWord}>
              <Text style={styles.exportText}>Ulashish</Text>
            </Pressable>
          </View>
        )}
        {!isLive && hasText && <Text style={styles.tip}>Matnni tuzatish uchun abzasni bosib turing · 🎙 — davom ettirish</Text>}
      </View>

      {/* Abzasni tahrirlash */}
      <Modal visible={!!editing} animationType="slide" transparent onRequestClose={() => setEditing(null)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Abzasni tahrirlash</Text>
            <TextInput style={styles.modalInput} value={editText} onChangeText={setEditText} multiline autoFocus />
            <View style={styles.modalRow}>
              <Pressable onPress={() => setEditing(null)} style={styles.modalBtn}>
                <Text style={styles.modalBtnText}>Bekor</Text>
              </Pressable>
              <Pressable onPress={saveEdit} style={[styles.modalBtn, { backgroundColor: colors.accent }]}>
                <Text style={[styles.modalBtnText, { color: '#fff' }]}>Saqlash</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Sarlavhani tahrirlash */}
      <Modal visible={titleEdit} animationType="fade" transparent onRequestClose={() => setTitleEdit(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Yozuv nomi</Text>
            <TextInput
              style={[styles.modalInput, { minHeight: 0 }]}
              defaultValue={doc.title}
              onChangeText={(v) => (titleRef.current = v)}
              autoFocus
              selectTextOnFocus
            />
            <View style={styles.modalRow}>
              <Pressable onPress={() => setTitleEdit(false)} style={styles.modalBtn}>
                <Text style={styles.modalBtnText}>Bekor</Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  const t = titleRef.current.trim() || doc.title;
                  setDoc((d) => ({ ...d, title: t }));
                  setTitleEdit(false);
                  persist(segments, doc.baseDurationMs, t).catch(() => {});
                }}
                style={[styles.modalBtn, { backgroundColor: colors.accent }]}
              >
                <Text style={[styles.modalBtnText, { color: '#fff' }]}>Saqlash</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {busy && (
        <View style={styles.busy}>
          <ActivityIndicator color="#fff" size="large" />
          <Text style={styles.busyText}>{busy}</Text>
        </View>
      )}
    </View>
  );
}

function RoundBtn({ label, sub, onPress, disabled }: { label: string; sub: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[styles.roundWrap, disabled && styles.disabled]}>
      <View style={styles.round}>
        <Text style={styles.roundLabel}>{label}</Text>
      </View>
      <Text style={styles.roundSub}>{sub}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  icon: { color: colors.text, fontSize: 24, width: 28, textAlign: 'center' },
  disabled: { opacity: 0.35 },
  title: { color: colors.text, fontSize: 17, fontWeight: '700' },
  status: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  banner: { paddingHorizontal: 16, paddingVertical: 10 },
  bannerText: { color: colors.text, fontSize: 14, lineHeight: 20 },
  footer: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
    paddingTop: 10,
    paddingBottom: 14,
    paddingHorizontal: 16,
  },
  timer: { color: colors.text, fontSize: 22, fontWeight: '300', textAlign: 'center', fontVariant: ['tabular-nums'] },
  controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  side: { width: 96, alignItems: 'center' },
  recBtn: {
    width: 78,
    height: 78,
    borderRadius: 39,
    backgroundColor: colors.rec,
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 12,
    borderWidth: 4,
    borderColor: '#ffffff22',
  },
  recBtnActive: { backgroundColor: '#C9303F', borderColor: '#FF4D5E66' },
  recIcon: { color: '#fff', fontSize: 28, fontWeight: '700' },
  roundWrap: { alignItems: 'center' },
  round: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  roundLabel: { color: colors.text, fontSize: 20 },
  roundSub: { color: colors.textDim, fontSize: 11, marginTop: 4 },
  exportRow: { flexDirection: 'row', gap: 10, marginTop: 14 },
  exportBtn: { flex: 1, paddingVertical: 13, borderRadius: 12, alignItems: 'center' },
  exportText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  tip: { color: colors.textFaint, fontSize: 11, textAlign: 'center', marginTop: 10 },
  modalWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: '#000a' },
  modal: { backgroundColor: colors.surface, padding: 16, borderTopLeftRadius: 16, borderTopRightRadius: 16 },
  modalTitle: { color: colors.text, fontSize: 17, fontWeight: '700', marginBottom: 12 },
  modalInput: {
    backgroundColor: colors.bg,
    color: colors.text,
    borderRadius: 10,
    padding: 12,
    fontSize: 16,
    minHeight: 160,
    maxHeight: 360,
    textAlignVertical: 'top',
  },
  modalRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  modalBtn: { flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center', backgroundColor: colors.surface2 },
  modalBtnText: { color: colors.text, fontSize: 15, fontWeight: '600' },
  busy: { ...StyleSheet.absoluteFill, backgroundColor: '#000a', alignItems: 'center', justifyContent: 'center' },
  busyText: { color: '#fff', marginTop: 12, fontSize: 15 },
});
