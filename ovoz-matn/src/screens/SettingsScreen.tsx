import { useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { DEFAULT_SONIOX_MODEL } from '../lib/soniox';
import type { Engine, Settings } from '../lib/storage';
import { LANGUAGE_LABELS } from '../lib/transcript';
import { colors } from '../theme';

interface Props {
  settings: Settings;
  onSave: (s: Settings) => void;
  onClose: () => void;
}

const DEVICE_LANGS: { code: Settings['deviceLang']; label: string }[] = [
  { code: 'uz-UZ', label: "O'zbekcha" },
  { code: 'ru-RU', label: 'Русский' },
  { code: 'en-US', label: 'English' },
];

function Chip({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.chip, active && styles.chipActive]}>
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

export default function SettingsScreen({ settings, onSave, onClose }: Props) {
  const [s, setS] = useState<Settings>(settings);
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS((p) => ({ ...p, [k]: v }));

  const toggleHint = (code: string) => {
    const has = s.languageHints.includes(code);
    const next = has ? s.languageHints.filter((c) => c !== code) : [...s.languageHints, code];
    if (next.length) set('languageHints', next);
  };

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Pressable onPress={onClose} hitSlop={12}>
          <Text style={styles.headerBtn}>Bekor</Text>
        </Pressable>
        <Text style={styles.headerTitle}>Sozlamalar</Text>
        <Pressable
          onPress={() => {
            onSave(s);
            onClose();
          }}
          hitSlop={12}
        >
          <Text style={[styles.headerBtn, { color: colors.accent, fontWeight: '700' }]}>Saqlash</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Text style={styles.section}>Nutq tanish rejimi</Text>
        <View style={styles.row}>
          {(['cloud', 'device'] as Engine[]).map((e) => (
            <Chip
              key={e}
              active={s.engine === e}
              label={e === 'cloud' ? '☁️ Bulut (avto til)' : '📱 Qurilma'}
              onPress={() => set('engine', e)}
            />
          ))}
        </View>
        <Text style={styles.hint}>
          {s.engine === 'cloud'
            ? "Bulut rejimida o'zbek, rus va ingliz tillari avtomatik aniqlanadi — hatto bitta gap ichida almashsa ham. Internet va Soniox API kaliti kerak."
            : "Qurilma rejimida telefonning o'z nutq tanish tizimi ishlatiladi. Til avtomatik aniqlanmaydi — quyida tanlang. Kalit kerak emas."}
        </Text>

        {s.engine === 'cloud' ? (
          <>
            <Text style={styles.section}>Soniox API kaliti</Text>
            <TextInput
              style={styles.input}
              value={s.sonioxApiKey}
              onChangeText={(v) => set('sonioxApiKey', v)}
              placeholder="API kalitni shu yerga qo'ying"
              placeholderTextColor={colors.textFaint}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
            />
            <Pressable onPress={() => Linking.openURL('https://console.soniox.com')}>
              <Text style={styles.link}>Kalit olish: console.soniox.com →</Text>
            </Pressable>

            <Text style={styles.section}>Kutilayotgan tillar</Text>
            <View style={styles.row}>
              {Object.entries(LANGUAGE_LABELS).map(([code, l]) => (
                <Chip
                  key={code}
                  active={s.languageHints.includes(code)}
                  label={`${l.flag} ${l.name}`}
                  onPress={() => toggleHint(code)}
                />
              ))}
            </View>

            <Text style={styles.section}>Maxsus atamalar (ixtiyoriy)</Text>
            <TextInput
              style={[styles.input, { minHeight: 70, textAlignVertical: 'top' }]}
              value={s.contextTerms}
              onChangeText={(v) => set('contextTerms', v)}
              placeholder="Ismlar, terminlar — vergul bilan: Toshkent, IT-park, KPI"
              placeholderTextColor={colors.textFaint}
              multiline
            />
            <Text style={styles.hint}>Ma'ruza mavzusiga oid so'zlar aniqlikni oshiradi.</Text>

            <Text style={styles.section}>Model</Text>
            <TextInput
              style={styles.input}
              value={s.sonioxModel}
              onChangeText={(v) => set('sonioxModel', v)}
              placeholder={DEFAULT_SONIOX_MODEL}
              placeholderTextColor={colors.textFaint}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </>
        ) : (
          <>
            <Text style={styles.section}>Til</Text>
            <View style={styles.row}>
              {DEVICE_LANGS.map((l) => (
                <Chip key={l.code} active={s.deviceLang === l.code} label={l.label} onPress={() => set('deviceLang', l.code)} />
              ))}
            </View>
          </>
        )}

        <Text style={styles.section}>Word fayl</Text>
        <View style={styles.switchRow}>
          <Text style={styles.switchLabel}>Vaqt belgilari [01:23]</Text>
          <Switch value={s.includeTimestamps} onValueChange={(v) => set('includeTimestamps', v)} />
        </View>
        <View style={styles.switchRow}>
          <Text style={styles.switchLabel}>Til belgilari [UZ] [RU] [EN]</Text>
          <Switch value={s.includeLanguageTags} onValueChange={(v) => set('includeLanguageTags', v)} />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  headerTitle: { color: colors.text, fontSize: 17, fontWeight: '700' },
  headerBtn: { color: colors.textDim, fontSize: 16 },
  body: { padding: 16, paddingBottom: 60 },
  section: { color: colors.textDim, fontSize: 13, fontWeight: '700', textTransform: 'uppercase', marginTop: 22, marginBottom: 10 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipText: { color: colors.textDim, fontSize: 14 },
  chipTextActive: { color: '#fff', fontWeight: '600' },
  hint: { color: colors.textFaint, fontSize: 13, marginTop: 8, lineHeight: 19 },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    color: colors.text,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  link: { color: colors.accent, marginTop: 8, fontSize: 14 },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8 },
  switchLabel: { color: colors.text, fontSize: 15 },
});
