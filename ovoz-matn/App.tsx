import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { DEFAULT_SETTINGS, loadSession, loadSettings, saveSettings, type SessionData, type Settings } from './src/lib/storage';
import HistoryScreen from './src/screens/HistoryScreen';
import RecorderScreen from './src/screens/RecorderScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { colors } from './src/theme';

type Screen = 'recorder' | 'settings' | 'history';

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [screen, setScreen] = useState<Screen>('recorder');
  const [opened, setOpened] = useState<SessionData | null>(null);

  useEffect(() => {
    loadSettings().then((s) => {
      setSettings(s);
      // Birinchi ishga tushishda kalit bo'lmasa — sozlamalarni ko'rsatamiz
      if (s.engine === 'cloud' && !s.sonioxApiKey) setScreen('settings');
    });
  }, []);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
        <StatusBar style="light" />
        {!settings ? (
          <ActivityIndicator style={{ flex: 1 }} color={colors.accent} />
        ) : (
          <>
            {/* Yozish ekrani doim xotirada turadi — yozuv uzilmasligi uchun */}
            <View style={[styles.fill, screen !== 'recorder' && styles.hidden]}>
              <RecorderScreen
                settings={settings}
                opened={opened}
                onConsumeOpened={() => setOpened(null)}
                onOpenSettings={() => setScreen('settings')}
                onOpenHistory={() => setScreen('history')}
              />
            </View>
            {screen === 'settings' && (
              <View style={styles.overlay}>
                <SettingsScreen
                  settings={settings ?? DEFAULT_SETTINGS}
                  onSave={(s) => {
                    setSettings(s);
                    saveSettings(s).catch(() => {});
                  }}
                  onClose={() => setScreen('recorder')}
                />
              </View>
            )}
            {screen === 'history' && (
              <View style={styles.overlay}>
                <HistoryScreen
                  onClose={() => setScreen('recorder')}
                  onOpen={async (id) => {
                    const data = await loadSession(id);
                    if (data) setOpened(data);
                    setScreen('recorder');
                  }}
                />
              </View>
            )}
          </>
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  fill: { flex: 1 },
  hidden: { display: 'none' },
  overlay: { ...StyleSheet.absoluteFill, backgroundColor: colors.bg },
});
