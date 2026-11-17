import { useEffect, useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, type ScrollViewInstance } from 'react-native';
import { formatTimestamp, langLabel, type Segment } from '../lib/transcript';
import { colors, langColor } from '../theme';

interface Props {
  segments: Segment[];
  pendingText?: string;
  pendingLang?: string;
  live?: boolean;
  showTimestamps?: boolean;
  placeholder?: string;
  onEditSegment?: (seg: Segment) => void;
}

export function LangBadge({ lang }: { lang?: string }) {
  const l = langLabel(lang);
  return (
    <View style={[styles.badge, { borderColor: langColor(lang) }]}>
      <Text style={[styles.badgeText, { color: langColor(lang) }]}>{l.short}</Text>
    </View>
  );
}

export default function TranscriptView({
  segments,
  pendingText = '',
  pendingLang,
  live,
  showTimestamps = true,
  placeholder,
  onEditSegment,
}: Props) {
  const scroll = useRef<ScrollViewInstance>(null);
  const followBottom = useRef(true);

  useEffect(() => {
    if (live && followBottom.current) scroll.current?.scrollToEnd({ animated: true });
  }, [segments, pendingText, live]);

  const last = segments[segments.length - 1];
  const pendingStartsNew = !!pendingText.trim() && (!last || (pendingLang && last.lang && pendingLang !== last.lang));
  const empty = segments.length === 0 && !pendingText.trim();

  return (
    <ScrollView
      ref={scroll}
      style={styles.scroll}
      contentContainerStyle={styles.content}
      onScroll={(e) => {
        const { layoutMeasurement, contentOffset, contentSize } = e.nativeEvent;
        followBottom.current = layoutMeasurement.height + contentOffset.y >= contentSize.height - 80;
      }}
      scrollEventThrottle={100}
    >
      {empty && <Text style={styles.placeholder}>{placeholder}</Text>}
      {segments.map((s, i) => {
        const isLast = i === segments.length - 1;
        return (
          <Pressable
            key={s.id}
            onLongPress={onEditSegment ? () => onEditSegment(s) : undefined}
            style={[styles.segment, { borderLeftColor: langColor(s.lang) }]}
          >
            <View style={styles.meta}>
              <LangBadge lang={s.lang} />
              {showTimestamps && s.startMs != null && <Text style={styles.time}>{formatTimestamp(s.startMs)}</Text>}
            </View>
            <Text style={styles.text} selectable={!live}>
              {s.text.trim()}
              {isLast && !pendingStartsNew && pendingText ? <Text style={styles.pending}>{pendingText}</Text> : null}
            </Text>
          </Pressable>
        );
      })}
      {pendingStartsNew && (
        <View style={[styles.segment, { borderLeftColor: langColor(pendingLang) }]}>
          <View style={styles.meta}>
            <LangBadge lang={pendingLang} />
          </View>
          <Text style={[styles.text, styles.pending]}>{pendingText.trimStart()}</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1 },
  content: { padding: 16, paddingBottom: 40 },
  placeholder: { color: colors.textFaint, fontSize: 16, textAlign: 'center', marginTop: 60, lineHeight: 24 },
  segment: { borderLeftWidth: 3, paddingLeft: 12, marginBottom: 18 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  time: { color: colors.textFaint, fontSize: 12, fontVariant: ['tabular-nums'] },
  text: { color: colors.text, fontSize: 18, lineHeight: 27 },
  pending: { color: colors.textDim, fontStyle: 'italic' },
  badge: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 1 },
  badgeText: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
});
