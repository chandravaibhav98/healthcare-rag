# Phase 11 Report: Playwright Demo Suite and Video

- **Date:** 2026-11-20 · **Plan ref:** `plan.md` §4 Phase 11 · Milestone M4 (part 1)
- **Result:** every deliverable is built. With nothing running beforehand,
  `scripts/demo-record.sh` (and `.ps1`) builds the index, starts a fresh seeded stack,
  records a narrated 10-chapter walkthrough and writes an **H.264 1920×1080 MP4** of
  about 3 min 40 s (≈6 MB) with embedded chapter markers, a chapter list and a GIF
  teaser. **Exit criterion met** in both shells.
- **Also:** the demo asserts every outcome it shows; the e2e TypeScript is now
  type-checked by `scripts/lint.*`; every GitHub Release gets the video attached
  (`demo.yml`).

## 1. Deliverables

| Deliverable | Where |
| --- | --- |
| Two Playwright projects. `e2e`: `tests/`, assertive, failure-only video. `demo`: `demo/`, video always on, 1920×1080 viewport and video, `slowMo` 120 ms, fixed locale/time zone/colour scheme, no retries | `e2e/playwright.config.ts` |
| `showCaption(page, text, ms)`. The hold time is never shorter than reading time (about 3 words/s). Also: `spotlight()` (outline, centred, moves the caption out of the way), a visible pointer with click ripples, `typeSlowly()`, `Chapters` (chapter times relative to video start) | `e2e/demo/captions.ts` |
| One test, ten `test.step` chapters plus a summary, paced waits, real assertions | `e2e/demo/demo.spec.ts` |
| Chapter writer: FFmpeg metadata (MP4 chapters) + `00:00 Title` list + teaser start | `e2e/demo/chapters.mjs` |
| `demo-record`: prerequisites → index from `corpus/` → recording on a fresh seeded stack → MP4 (`-preset veryfast`, CRF 20, `+faststart`, chapters) → optional GIF → ffprobe checks (H.264, 1920×1080, ≥10 chapters) | `scripts/demo-record.{sh,ps1}` |
| `--candidate-index`: the disposable E2E API also builds a second index version, so the demo can activate it and roll back | `backend/scripts/e2e_server.py` |
| Demo video workflow, manual or called by `release.yml` to attach MP4, GIF and chapters to the release | `.github/workflows/demo.yml`, `release.yml` |
| `npm test` runs only `e2e`; `npm run demo`, `npm run typecheck`. `scripts/lint.*` type-check `e2e/` | `e2e/package.json`, `scripts/lint.{sh,ps1}` |
| Docs | `e2e/README.md` (chapter table), README, `plan.md` |

### Storyboard as recorded

| Chapter | Starts at | What happens (all asserted) |
| --- | --- | --- |
| 1 | 0:00 | Assistant, disclaimer spotlighted |
| 2 | 0:10 | "When should an N95 respirator be discarded?" → **validated** (0.84); confidence breakdown opened from the keyboard |
| 3 | 0:39 | Evidence panel: 17/17 key words highlighted, numeric check |
| 4 | 0:53 | "What temperature range should refrigerated vaccines be stored at?" → **validated** (0.87), cited from CDC, WHO and NIH; 2–8 °C passes the numeric check |
| 5 | 1:12 | "Which antibiotic should be used for community-acquired pneumonia?" → **needs review** (0.42), escalated with a note |
| 6 | 1:38 | Admin sign-in, Overview KPIs |
| 7 | 1:59 | Review queue: the escalated item, approve + promote to gold, saved |
| 8 | 2:19 | Evaluation trend and threshold sweep; a run started on camera finishes and adds a row |
| 9 | 2:43 | Index versions: activate `bfae4024806c`, then roll back to `6ce73ffaf982` |
| 10 | 3:06 | Threshold 0.60 → 0.65 with impact preview; the `config.update` row appears in the audit log |

The questions were chosen by running candidates against the deterministic index, so
each one always gives the same outcome. The unsupported question is deliberately
near-domain (clinical, with related sources) rather than off-topic: it shows that the
assistant declines to answer, not merely that it finds nothing. The yellow-fever
question from OI-27 was avoided, because it is falsely validated at τ = 0.6.

## 2. Verification

| Check | Result |
| --- | --- |
| `scripts/demo-record.sh --gif` from an empty `artifacts/` | ✅ MP4 h264 1920×1080, 220 s, 11 chapters, 5.8 MB; GIF; chapter list; index `6ce73ffaf982` checked against the build |
| `scripts/demo-record.ps1 --gif` (pwsh 7) from an empty `artifacts/` | ✅ same checks |
| Frames reviewed at every chapter | Captions readable; pointer and ripples visible; spotlighted elements no longer hidden by the caption (§3) |
| `npm --prefix e2e test` after the project split | 20/20, `demo` not run |
| `tsc -p e2e`, prettier, `shellcheck`, `actionlint` (with `demo.yml`) | Clean |
| Recording repeated three times | Same chapters within ±1 s; same outcomes |

## 3. Defects found while building

| Defect | Fix |
| --- | --- |
| The caption covered the third source while the narration talked about it (chapter 4) | `spotlight()` centres the element and moves the caption to the top when that hides less of it |
| Chapter captions were held on the previous page before navigating, so "Review queue" was read over the Overview | Navigate first, then announce the chapter |
| `ffmpeg -encoders \| grep -q libx264` failed under `pipefail` (grep closes the pipe early, ffmpeg gets SIGPIPE) | Capture the output, then match |
| `npm test` would have run the 4-minute demo with the functional suite | `npm test` = `--project=e2e` |
| The e2e TypeScript was never type-checked anywhere | `npm run typecheck` in `e2e/`, wired into `scripts/lint.*` |

## 4. Open issues

| # | Change |
| --- | --- |
| OI-37 | Extended. In the sandbox, Playwright recorded through the system ffmpeg (its own build could not be downloaded). On a developer machine and in CI, `playwright install` provides it; `demo-record` runs `playwright install ffmpeg` first |
| OI-41 | **New, minor:** the demo changes data (a review, a config version, an evaluation run), so `--target` must point at a disposable stack. This is documented in `--help` and the README |

## 5. How this was verified

Linux sandbox. Repository at c340ba6 plus the Phase 11 changes; Node 26.7, Playwright
1.65.1 driving Chrome 153, ffmpeg 6.1 (libx264), pwsh 7.
