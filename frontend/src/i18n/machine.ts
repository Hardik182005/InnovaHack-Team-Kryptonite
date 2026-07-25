/** Machine translation for strings the curated dictionaries do not cover.
 *
 * `strings.ts` carries reviewed wording for a few languages. The selector
 * offers all 22 scheduled languages, and every key added after a dictionary was
 * written is missing from it — in both cases `translate()` falls back to
 * English, which is what "some things are not translating" looks like on screen.
 *
 * This module closes that gap without anyone hand-writing another dictionary:
 * on a language switch it posts the missing English strings to the backend in
 * one batch, stores what comes back, and tells React to re-render.
 *
 * Precedence is deliberate and never changes:
 *
 *     curated string  >  machine translation  >  English
 *
 * A reviewed translation always wins, so nothing here can overwrite wording
 * that a person approved — machine output only ever reaches a slot that would
 * otherwise have displayed English.
 */

import { API_BASE_URL } from '../api/config';

const STORAGE_PREFIX = 'safespare.mt.';

/** language -> (english source -> translated) */
const memory = new Map<string, Record<string, string>>();
const listeners = new Set<() => void>();
const inflight = new Set<string>();

function notify(): void {
  listeners.forEach((fn) => fn());
}

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function load(lang: string): Record<string, string> {
  const cached = memory.get(lang);
  if (cached) return cached;
  let parsed: Record<string, string> = {};
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + lang);
    if (raw) parsed = JSON.parse(raw) as Record<string, string>;
  } catch {
    /* corrupt or unavailable storage just means we translate again */
  }
  memory.set(lang, parsed);
  return parsed;
}

function persist(lang: string, table: Record<string, string>): void {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + lang, JSON.stringify(table));
  } catch {
    /* over quota — the in-memory copy still serves this session */
  }
}

/** The translation for `source`, or null if we do not have one yet. */
export function lookup(lang: string, source: string): string | null {
  if (lang === 'en') return null;
  return load(lang)[source] ?? null;
}

/**
 * Translate `sources` into `lang`, skipping anything already known.
 *
 * Safe to call on every render: it de-duplicates against both the cache and
 * the request already in flight, so a burst of components asking for the same
 * language produces exactly one network call.
 */
export async function request(lang: string, sources: string[]): Promise<void> {
  if (lang === 'en' || sources.length === 0) return;

  const table = load(lang);
  const missing = Array.from(
    new Set(sources.filter((s) => s && s.trim() && table[s] === undefined)),
  );
  if (missing.length === 0) return;

  // The backend caps a batch; chunking here keeps a large first switch from
  // being rejected wholesale and losing every string in it.
  const CHUNK = 100;
  for (let i = 0; i < missing.length; i += CHUNK) {
    const batch = missing.slice(i, i + CHUNK);
    const key = lang + ':' + i + ':' + batch.length;
    if (inflight.has(key)) continue;
    inflight.add(key);

    try {
      const res = await fetch(`${API_BASE_URL}/api/translate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts: batch, target: lang }),
      });
      if (!res.ok) continue;

      const data = (await res.json()) as {
        translations?: { text: string; source: string }[];
      };
      const out = data.translations ?? [];
      if (out.length !== batch.length) continue;

      let changed = false;
      out.forEach((entry, idx) => {
        const original = batch[idx];
        // `passthrough` means the provider was unavailable and handed the
        // English straight back. Recording it would cache a non-translation
        // forever and permanently mask the string, so it is dropped instead
        // and retried on the next switch.
        if (entry.source === 'passthrough' || entry.text === original) return;
        table[original] = entry.text;
        changed = true;
      });

      if (changed) {
        persist(lang, table);
        notify();
      }
    } catch {
      /* offline or backend down — English remains on screen, which is fine */
    } finally {
      inflight.delete(key);
    }
  }
}
