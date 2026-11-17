/**
 * Transkriptni Microsoft Word (.docx) hujjatiga aylantirish.
 */
import { AlignmentType, Document, HeadingLevel, Packer, Paragraph, TextRun } from 'docx';
import { detectedLanguages, formatTimestamp, langLabel, type Segment } from './transcript';

export interface DocxOptions {
  title: string;
  createdAt: number;
  durationMs?: number;
  includeTimestamps: boolean;
  includeLanguageTags: boolean;
}

function formatDate(ts: number) {
  const d = new Date(ts);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function buildDocument(segments: Segment[], opts: DocxOptions): Document {
  const langs = detectedLanguages(segments)
    .map((l) => langLabel(l).name)
    .join(', ');

  const meta: string[] = [`Sana: ${formatDate(opts.createdAt)}`];
  if (opts.durationMs) meta.push(`Davomiyligi: ${formatTimestamp(opts.durationMs)}`);
  if (langs) meta.push(`Tillar: ${langs}`);

  const body = segments
    .filter((s) => s.text.trim())
    .map((s) => {
      const runs: TextRun[] = [];
      const prefix: string[] = [];
      if (opts.includeTimestamps && s.startMs != null) prefix.push(`[${formatTimestamp(s.startMs)}]`);
      if (opts.includeLanguageTags && s.lang) prefix.push(`[${langLabel(s.lang).short}]`);
      if (prefix.length) runs.push(new TextRun({ text: prefix.join(' ') + ' ', bold: true, color: '666666' }));
      runs.push(new TextRun({ text: s.text.trim() }));
      return new Paragraph({ children: runs, spacing: { after: 160 }, alignment: AlignmentType.JUSTIFIED });
    });

  return new Document({
    creator: 'Ovoz → Matn',
    title: opts.title,
    description: 'Nutqdan avtomatik olingan matn',
    styles: {
      default: { document: { run: { font: 'Times New Roman', size: 28 } } }, // 14 pt
    },
    sections: [
      {
        children: [
          new Paragraph({ text: opts.title, heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER }),
          new Paragraph({
            children: [new TextRun({ text: meta.join('   •   '), italics: true, color: '777777', size: 22 })],
            alignment: AlignmentType.CENTER,
            spacing: { after: 300 },
          }),
          ...(body.length ? body : [new Paragraph({ text: '(matn yo‘q)' })]),
        ],
      },
    ],
  });
}

/** .docx faylning base64 ko'rinishi (expo-file-system orqali yozish uchun). */
export async function buildDocxBase64(segments: Segment[], opts: DocxOptions): Promise<string> {
  return Packer.toBase64String(buildDocument(segments, opts));
}

/** Fayl nomi uchun xavfsiz qatorga aylantiradi. */
export function safeFileName(title: string, createdAt: number): string {
  const d = new Date(createdAt);
  const pad = (n: number) => n.toString().padStart(2, '0');
  const stamp = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}`;
  const base = title
    .replace(/[\\/:*?"<>|\n\r\t]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 60);
  return `${base || 'Transkript'}_${stamp}.docx`;
}
