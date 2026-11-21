/**
 * Narration for the recorded demo (plan Phase 11).
 *
 * Playwright's video has no sound and no mouse pointer, so the demo injects its own:
 *   - a caption banner (chapter counter, title, one line of narration) at the bottom,
 *   - a pointer that follows the real mouse events, with a ripple on every click,
 *   - `spotlight()`, a temporary outline around the element being talked about.
 * All of it is decoration: `pointer-events: none`, `aria-hidden`, and it survives full
 * page loads (the init script re-creates it and restores the last caption).
 *
 * `Chapters` records when each step starts, relative to the start of the video, so
 * scripts/demo-record.* can write chapter markers into the MP4 and demo-chapters.txt.
 */
import { writeFileSync } from 'node:fs';

import type { Locator, Page } from '@playwright/test';

const OVERLAY_ID = '__demo-overlay';

/** Runs in the page before any app script, on every document. */
function overlayInit(id: string): void {
  const install = (): void => {
    if (document.getElementById(id)) return;
    const root = document.createElement('div');
    root.id = id;
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = `
      <style>
        #${id} { position: fixed; inset: 0; pointer-events: none; z-index: 2147483647;
          font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
        #${id} .cap { position: absolute; left: 50%; bottom: 36px; transform: translateX(-50%);
          max-width: 1400px; padding: 18px 30px; border-radius: 14px;
          background: rgba(15, 23, 42, 0.92); color: #f8fafc;
          box-shadow: 0 12px 32px rgba(0,0,0,.35); opacity: 0; transition: opacity .35s ease; }
        #${id} .cap.on { opacity: 1; }
        #${id} .cap.top { bottom: auto; top: 76px; }
        #${id} .step { font-size: 15px; letter-spacing: .08em; text-transform: uppercase;
          color: #7dd3fc; margin-bottom: 4px; }
        #${id} .title { font-size: 30px; font-weight: 700; line-height: 1.2; }
        #${id} .text { font-size: 22px; line-height: 1.35; margin-top: 6px; color: #cbd5e1; }
        #${id} .ptr { position: absolute; width: 22px; height: 22px; margin: -11px 0 0 -11px;
          border-radius: 50%; background: rgba(239, 68, 68, .55); border: 2px solid #fff;
          box-shadow: 0 0 0 1px rgba(0,0,0,.35); left: -100px; top: -100px;
          transition: left .18s ease, top .18s ease; }
        #${id} .ripple { position: absolute; width: 22px; height: 22px; margin: -11px 0 0 -11px;
          border-radius: 50%; border: 3px solid rgba(239, 68, 68, .9);
          animation: demo-ripple .6s ease-out forwards; }
        @keyframes demo-ripple { to { transform: scale(3.2); opacity: 0; } }
        .__demo-spot { outline: 4px solid #f59e0b !important; outline-offset: 4px !important;
          border-radius: 6px; transition: outline-color .3s ease; }
      </style>
      <div class="cap"><div class="step"></div><div class="title"></div><div class="text"></div></div>
      <div class="ptr"></div>`;
    document.documentElement.appendChild(root);

    const ptr = root.querySelector<HTMLElement>('.ptr');
    document.addEventListener(
      'mousemove',
      (e) => {
        if (!ptr) return;
        ptr.style.left = `${e.clientX.toString()}px`;
        ptr.style.top = `${e.clientY.toString()}px`;
      },
      { capture: true, passive: true },
    );
    document.addEventListener(
      'mousedown',
      (e) => {
        const r = document.createElement('div');
        r.className = 'ripple';
        r.style.left = `${e.clientX.toString()}px`;
        r.style.top = `${e.clientY.toString()}px`;
        root.appendChild(r);
        setTimeout(() => {
          r.remove();
        }, 700);
      },
      { capture: true, passive: true },
    );

    // Restore the caption after a full page load (page.goto, sign-in redirects).
    const saved = sessionStorage.getItem(id);
    if (saved) render(JSON.parse(saved) as Caption);
  };

  type Caption = { step: string; title: string; text: string };
  const render = (c: Caption | null): void => {
    const cap = document.querySelector<HTMLElement>(`#${id} .cap`);
    if (!cap) return;
    cap.classList.remove('top');
    if (!c) {
      cap.classList.remove('on');
      return;
    }
    cap.querySelector('.step')!.textContent = c.step;
    cap.querySelector('.title')!.textContent = c.title;
    cap.querySelector('.text')!.textContent = c.text;
    cap.classList.add('on');
  };
  (window as unknown as { __demoCaption: (c: Caption | null) => void }).__demoCaption = (c) => {
    install();
    if (c) sessionStorage.setItem(id, JSON.stringify(c));
    else sessionStorage.removeItem(id);
    render(c);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    install();
  }
}

export async function installOverlay(page: Page): Promise<void> {
  await page.addInitScript(overlayInit, OVERLAY_ID);
}

export interface CaptionText {
  /** e.g. "2 / 10" */
  step?: string;
  title: string;
  text?: string;
}

/**
 * Show a caption and hold for `ms` so the viewer can read it. Reading speed is about
 * 3 words per second, so the hold is never shorter than the text needs.
 */
export async function showCaption(page: Page, caption: CaptionText | string, ms = 2500) {
  const c = typeof caption === 'string' ? { title: caption } : caption;
  const payload = { step: c.step ?? '', title: c.title, text: c.text ?? '' };
  await page.evaluate((p) => {
    (window as unknown as { __demoCaption: (x: typeof p) => void }).__demoCaption(p);
  }, payload);
  const words = `${payload.title} ${payload.text}`.split(/\s+/).length;
  await page.waitForTimeout(Math.max(ms, Math.round((words / 3) * 1000)));
}

export async function hideCaption(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __demoCaption: (x: null) => void }).__demoCaption(null);
  });
}

/**
 * Outline an element for `ms`, then remove the outline. The element is scrolled to the
 * middle of the screen, and if the caption would cover it the caption moves to the top.
 */
export async function spotlight(target: Locator, ms = 1800): Promise<void> {
  await target.evaluate((el, id) => {
    el.scrollIntoView({ block: 'center', inline: 'nearest' });
    el.classList.add('__demo-spot');
    const cap = document.querySelector<HTMLElement>(`#${id} .cap`);
    if (cap?.classList.contains('on')) {
      // Put the caption where it hides less of the element: bottom (default) or top.
      cap.classList.remove('top');
      const r = el.getBoundingClientRect();
      const c = cap.getBoundingClientRect();
      const hidden = (top: number) =>
        Math.max(0, Math.min(r.bottom, top + c.height) - Math.max(r.top, top));
      cap.classList.toggle('top', hidden(76) < hidden(c.top));
    }
  }, OVERLAY_ID);
  await target.page().waitForTimeout(ms);
  await target.evaluate((el) => {
    el.classList.remove('__demo-spot');
  });
}

/** Move the visible pointer to an element without clicking (a "look here" gesture). */
export async function pointAt(target: Locator, ms = 600): Promise<void> {
  await target.scrollIntoViewIfNeeded();
  await target.hover();
  await target.page().waitForTimeout(ms);
}

/** Type like a person, so the question appears on screen as it is asked. */
export async function typeSlowly(target: Locator, text: string): Promise<void> {
  await target.click();
  await target.fill('');
  await target.pressSequentially(text, { delay: 28 });
}

export interface Chapter {
  title: string;
  startMs: number;
}

/** Chapter start times relative to the video start (the page's creation). */
export class Chapters {
  private readonly items: Chapter[] = [];

  constructor(private readonly videoStart: number) {}

  mark(title: string): void {
    this.items.push({ title, startMs: Math.max(0, Date.now() - this.videoStart) });
  }

  /** JSON for scripts/demo-record.* (MP4 chapters and demo-chapters.txt). */
  write(path: string, totalMs = Date.now() - this.videoStart): void {
    writeFileSync(path, JSON.stringify({ totalMs, chapters: this.items }, null, 2));
  }
}
