import { useEffect, useState } from 'react';
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { deleteSession, listSessions, type SessionMeta } from '../lib/storage';
import { formatTimestamp } from '../lib/transcript';
import { LangBadge } from '../components/TranscriptView';
import { colors } from '../theme';

interface Props {
  onOpen: (id: string) => void;
  onClose: () => void;
}

export default function HistoryScreen({ onOpen, onClose }: Props) {
  const [items, setItems] = useState<SessionMeta[] | null>(null);

  const reload = () => listSessions().then(setItems);
  useEffect(() => {
    reload();
  }, []);

  const confirmDelete = (item: SessionMeta) =>
    Alert.alert("O'chirish", `"${item.title}" o'chirilsinmi?`, [
      { text: 'Yo‘q', style: 'cancel' },
      { text: "O'chirish", style: 'destructive', onPress: () => deleteSession(item.id).then(reload) },
    ]);

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Pressable onPress={onClose} hitSlop={12}>
          <Text style={styles.back}>‹ Orqaga</Text>
        </Pressable>
        <Text style={styles.title}>Saqlangan yozuvlar</Text>
        <View style={{ width: 70 }} />
      </View>
      <FlatList
        data={items ?? []}
        keyExtractor={(i) => i.id}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={items ? <Text style={styles.empty}>Hozircha yozuvlar yo'q</Text> : undefined}
        renderItem={({ item }) => (
          <Pressable style={styles.card} onPress={() => onOpen(item.id)} onLongPress={() => confirmDelete(item)}>
            <View style={styles.cardTop}>
              <Text style={styles.cardTitle} numberOfLines={1}>
                {item.title}
              </Text>
              <Text style={styles.cardDur}>{formatTimestamp(item.durationMs)}</Text>
            </View>
            <Text style={styles.preview} numberOfLines={2}>
              {item.preview || '—'}
            </Text>
            <View style={styles.cardBottom}>
              <Text style={styles.date}>{new Date(item.createdAt).toLocaleString()}</Text>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                {item.langs.map((l) => (
                  <LangBadge key={l} lang={l} />
                ))}
              </View>
            </View>
          </Pressable>
        )}
      />
      <Text style={styles.footer}>O'chirish uchun yozuvni bosib turing</Text>
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
  back: { color: colors.accent, fontSize: 16, width: 70 },
  title: { color: colors.text, fontSize: 17, fontWeight: '700' },
  empty: { color: colors.textFaint, textAlign: 'center', marginTop: 60, fontSize: 15 },
  card: { backgroundColor: colors.surface, borderRadius: 12, padding: 14, marginBottom: 12 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 },
  cardTitle: { color: colors.text, fontSize: 16, fontWeight: '600', flex: 1 },
  cardDur: { color: colors.textDim, fontSize: 13, fontVariant: ['tabular-nums'] },
  preview: { color: colors.textDim, fontSize: 14, marginTop: 6, lineHeight: 20 },
  cardBottom: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 },
  date: { color: colors.textFaint, fontSize: 12 },
  footer: { color: colors.textFaint, fontSize: 12, textAlign: 'center', paddingBottom: 12 },
});
