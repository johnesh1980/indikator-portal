import { Directory, File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';
import { buildDocxBase64, safeFileName, type DocxOptions } from './docx';
import type { Segment } from './transcript';

const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

/** Word faylni ilova papkasiga yozadi va fayl obyektini qaytaradi. */
export async function writeDocx(segments: Segment[], opts: DocxOptions): Promise<File> {
  const base64 = await buildDocxBase64(segments, opts);
  const dir = new Directory(Paths.document, 'transkriptlar');
  if (!dir.exists) dir.create({ intermediates: true });
  const file = new File(dir, safeFileName(opts.title, opts.createdAt));
  if (file.exists) file.delete();
  file.create();
  file.write(base64, { encoding: 'base64' });
  return file;
}

/** Word faylni ulashish oynasi orqali yuborish (Telegram, Drive, Fayllar…). */
export async function shareDocx(segments: Segment[], opts: DocxOptions): Promise<void> {
  const file = await writeDocx(segments, opts);
  if (!(await Sharing.isAvailableAsync())) {
    throw new Error("Bu qurilmada ulashish imkoniyati yo'q");
  }
  await Sharing.shareAsync(file.uri, {
    mimeType: DOCX_MIME,
    dialogTitle: 'Word faylni saqlash yoki yuborish',
    UTI: 'org.openxmlformats.wordprocessingml.document',
  });
}

/**
 * Android: foydalanuvchi tanlagan papkaga (masalan, Download) to'g'ridan-to'g'ri saqlash.
 * iOS'da ulashish oynasidagi "Fayllarga saqlash" ishlatiladi.
 * Saqlangan fayl nomini qaytaradi, bekor qilinsa null.
 */
export async function saveDocxToFolder(segments: Segment[], opts: DocxOptions): Promise<string | null> {
  if (Platform.OS !== 'android') {
    await shareDocx(segments, opts);
    return null;
  }
  let target: Directory;
  try {
    target = await Directory.pickDirectoryAsync();
  } catch {
    return null; // foydalanuvchi bekor qildi
  }
  const base64 = await buildDocxBase64(segments, opts);
  const name = safeFileName(opts.title, opts.createdAt);
  const out = target.createFile(name.replace(/\.docx$/, ''), DOCX_MIME);
  out.write(base64, { encoding: 'base64' });
  return name;
}
