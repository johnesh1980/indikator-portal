import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEFAULT_SONIOX_MODEL } from './soniox';
import type { Segment } from './transcript';

export type Engine = 'cloud' | 'device';

export interface Settings {
  engine: Engine;
  sonioxApiKey: string;
  sonioxModel: string;
  /** Avto aniqlashda kutiladigan tillar */
  languageHints: string[];
  /** Qurilma rejimida tanlangan til (avto aniqlash yo'q) */
  deviceLang: 'uz-UZ' | 'ru-RU' | 'en-US';
  contextTerms: string;
  includeTimestamps: boolean;
  includeLanguageTags: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  engine: 'cloud',
  sonioxApiKey: '',
  sonioxModel: DEFAULT_SONIOX_MODEL,
  languageHints: ['uz', 'ru', 'en'],
  deviceLang: 'uz-UZ',
  contextTerms: '',
  includeTimestamps: true,
  includeLanguageTags: true,
};

export interface SessionMeta {
  id: string;
  title: string;
  createdAt: number;
  durationMs: number;
  preview: string;
  langs: string[];
}

export interface SessionData extends SessionMeta {
  segments: Segment[];
}

const K_SETTINGS = 'ovozmatn:settings';
const K_INDEX = 'ovozmatn:sessions';
const kSession = (id: string) => `ovozmatn:session:${id}`;

export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await AsyncStorage.getItem(K_SETTINGS);
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export async function saveSettings(s: Settings) {
  await AsyncStorage.setItem(K_SETTINGS, JSON.stringify(s));
}

export async function listSessions(): Promise<SessionMeta[]> {
  try {
    const raw = await AsyncStorage.getItem(K_INDEX);
    const list: SessionMeta[] = raw ? JSON.parse(raw) : [];
    return list.sort((a, b) => b.createdAt - a.createdAt);
  } catch {
    return [];
  }
}

export async function loadSession(id: string): Promise<SessionData | null> {
  const raw = await AsyncStorage.getItem(kSession(id));
  return raw ? JSON.parse(raw) : null;
}

export async function saveSession(data: SessionData) {
  const meta: SessionMeta = {
    id: data.id,
    title: data.title,
    createdAt: data.createdAt,
    durationMs: data.durationMs,
    preview: data.preview,
    langs: data.langs,
  };
  await AsyncStorage.setItem(kSession(data.id), JSON.stringify(data));
  const list = (await listSessions()).filter((s) => s.id !== data.id);
  list.unshift(meta);
  await AsyncStorage.setItem(K_INDEX, JSON.stringify(list));
}

export async function deleteSession(id: string) {
  await AsyncStorage.removeItem(kSession(id));
  const list = (await listSessions()).filter((s) => s.id !== id);
  await AsyncStorage.setItem(K_INDEX, JSON.stringify(list));
}
