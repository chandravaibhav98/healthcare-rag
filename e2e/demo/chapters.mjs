#!/usr/bin/env node
/**
 * chapters.mjs CHAPTERS_JSON OUT_PREFIX
 *
 * Turns the chapter times recorded by demo.spec.ts (chapters.json) into:
 *   OUT_PREFIX.ffmeta        FFmpeg metadata, so the MP4 has real chapter markers
 *   OUT_PREFIX.chapters.txt  "00:00 Title" lines (video description / YouTube format)
 * and prints the start of chapter 2 in seconds (the GIF teaser starts there).
 *
 * Node rather than Python because Node is already required to record the demo, on both
 * scripts/demo-record.sh and .ps1.
 */
import { readFileSync, writeFileSync } from 'node:fs';

const [input, prefix] = process.argv.slice(2);
if (!input || !prefix) {
  console.error('usage: chapters.mjs CHAPTERS_JSON OUT_PREFIX');
  process.exit(2);
}

/** @type {{ totalMs: number, chapters: { title: string, startMs: number }[] }} */
const data = JSON.parse(readFileSync(input, 'utf8'));
if (!Array.isArray(data.chapters) || data.chapters.length === 0) {
  console.error(`${input}: no chapters`);
  process.exit(1);
}
// The first chapter covers the opening frames too (players expect a chapter at 0:00).
const chapters = data.chapters.map((c, i) => ({ ...c, startMs: i === 0 ? 0 : c.startMs }));
const ends = chapters.map((c, i) => (chapters[i + 1]?.startMs ?? data.totalMs) - 1);

const escape = (s) => s.replace(/[=;#\\\n]/g, (ch) => `\\${ch}`);
const ffmeta = [
  ';FFMETADATA1',
  'title=Healthcare Guidelines RAG Assistant: product demo',
  'comment=Synthetic guideline corpus. Not for clinical use.',
  ...chapters.flatMap((c, i) => [
    '',
    '[CHAPTER]',
    'TIMEBASE=1/1000',
    `START=${c.startMs.toString()}`,
    `END=${Math.max(ends[i], c.startMs + 1).toString()}`,
    `title=${escape(c.title)}`,
  ]),
].join('\n');
writeFileSync(`${prefix}.ffmeta`, `${ffmeta}\n`);

const stamp = (ms) => {
  const s = Math.floor(ms / 1000);
  const mm = Math.floor(s / 60)
    .toString()
    .padStart(2, '0');
  const ss = (s % 60).toString().padStart(2, '0');
  return `${mm}:${ss}`;
};
writeFileSync(
  `${prefix}.chapters.txt`,
  `${chapters.map((c) => `${stamp(c.startMs)} ${c.title}`).join('\n')}\n`,
);

const second = chapters[1] ?? chapters[0];
process.stdout.write(`${(second.startMs / 1000).toFixed(1)}\n`);
