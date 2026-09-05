# Stable release — starting point at `flatland-association`

> Proposal for a lean, curated starting point ahead of moving this repository
> to the `flatland-association` GitHub org. Grounded in a full diff/build/test
> pass on 2026-08-29 (`git diff --stat origin/main...explore_db`, `ng build
> --configuration production`, `pytest`), not estimation. Status: **overtaken
> in part — see §0.1** — `main` and `explore_db` merged (unreduced) while this
> was in progress; the reduction itself has not happened yet.

---

## 0. The decision

Don't fast-forward `explore_db` into `main` *unreduced*. Cut a
**`release/…`** branch, do the reduction and the blocker fixes on it, merge
*that* into `main`. `explore_db` keeps running unchanged (E1 variants, the HF
Space mirror) — the release branch's diff against it doubles as the changelog
of what a stable start deliberately leaves out.

### 0.1 What actually happened since (2026-08-30 → 2026-09-03)

The recommendation above was overtaken before it could be acted on:
**[PR #46](https://github.com/aiAdrian/flatland_ui/pull/46) merged `explore_db`
into `main` on 2026-08-30, unreduced.** `origin/main` and `origin/explore_db`
are now the same commit (`622e118`) — confirmed by `git diff origin/main
explore_db` returning empty. Everything §1 proposed dropping (the
personally-bound HF workflow, the duplicated scene JSONs, `PLAYGROUND.md`'s
fork framing, the `docs/reading`/`delegation`/`archive` question) is on `main`
now, not held back on a side branch.

The four completed blockers (§3) were done on a separate **`enabler`** branch,
cut from `explore_db` *before* the PR #46 merge and pushed to `origin/enabler`
(commit `7b3b12a`). It has since diverged from `main`/`explore_db` — both sides
share `bc1ff50` as the last common ancestor, `main` gained only the (content-
empty) merge commit, `enabler` gained the blocker fixes. Checked with
`git merge-tree`: merging `enabler` into `main` today produces **no
conflicts** in any of the six changed files.

**So the reduction proposed in §1 still has not happened** — it now has to
target `main` directly (or a branch cut from it) rather than protecting a
clean `main` from an unreduced merge. The plan below is otherwise unchanged
and still the intended shape of a stable start.

Earlier framing considered removing **E1 (Combined Actions)** as part of the
reduction. Measurement overturned that: E1 hangs off six files outside its own
directories (`session.store.ts`, `widget-catalog.ts`, `layout-presets.ts`,
`panel-plugin-host.component.ts`, `marey-chart.component.ts`,
`layout-designer.component.ts`) and the backend work behind it
(`conflict_detector.py`, `contention_cache.py`, `api/hmi.py`) is independently
useful — cutting it would either drag real work out or leave a stub API.
The Widgets Gallery already solves the "is this real" problem the widget
catalog's own `status`/`dataSource` fields, which the gallery filters and
labels (`mock`, `first-cut`, `planned` are never silently hidden — v1's
default-to-`shipped` filter that hid 8/33 widgets was deliberately reverted).
Honest labelling beats deletion for a consortium start.

So the reduction below is almost entirely **docs and personally-bound
infrastructure**, not application code.

---

## 1. What the release branch drops

| Drop | Size | Why | Stays on |
|---|---:|---|---|
| `.github/workflows/deploy-hf-space.yml` + `deploy/hf/` + `docs/deploy-hugging-face-space.md` | 3 files | `if: github.actor == 'danib8005'`, default Space `danib8005/…` — personally bound, dead/confusing code in an org repo | `explore_db` |
| ~~`docs/infrastructure_builder/scenes/*.scene.json`~~ | 724 KB, 3 files | byte-identical duplicates of `backend/app/fixtures/pf_ch/*.scene.json` (verified `diff -q`); zero references anywhere except this table | **done** (2026-09-05) — removed directly on `main`, ahead of the rest of this reduction |
| `PLAYGROUND.md` | 1 file | describes a diff against an `upstream/experiment/vibecoding-playground` relationship that won't exist after the move | `explore_db` (already partly de-staled, see §3) |
| `docs/reading/`, `docs/delegation/`, `docs/archive/` | 240 KB, 17 files | internal workshop/review notes and AI-delegation prompts — **open question, see §4**, not yet decided | `explore_db` |

Kept deliberately: `docs/media/` (5.7 MB GIF+MP4 — the README's showcase), all
7 `planned` and 8 `first-cut` widgets (correctly labelled, not hidden), E1 in
all three variants (see above).

---

## 2. Verified baseline (2026-08-29, superseded by §0.1 on 2026-08-30)

- `explore_db` was **48 commits ahead of `origin/main`**, `main` a strict
  ancestor → mechanically fast-forwardable, which is exactly what happened
  three days later via PR #46 (§0.1) — before the reduction below was acted
  on.
- `ng build --configuration production`: **green**. 3 warnings (unused
  `LayoutViewTogglePanelComponent` import, a redundant `??` in
  `survey.component.html`, initial bundle 1.71 MB vs. 1.20 MB budget).
- `pytest` (with `requirements-dev.txt`, torch installed): **308 passed, 2
  skipped, 0 failed.** (An initial run without `requirements-dev.txt` showed 9
  failures — all `ModuleNotFoundError: torch`, i.e. a missing dev dependency,
  not a real failure.)
- Of the +116k lines `explore_db` adds over `main`, ~103k are the seven scene
  JSON fixtures — three of which are the duplicates in §1.
- Widget registry: 25 `shipped`, 8 `first-cut`, 7 `planned`; 4 with
  `dataSource: 'mock'` (all correctly disclosed inline, e.g. widget-catalog.ts
  E1's "⚠ The prediction itself is a deterministic **mock**").
- No secrets, tokens, or `/Users/…` paths found in tracked files
  (`git grep` sweep for `hf_`/`ghp_` token shapes and local paths).

---

## 3. Blockers — status

Six blockers were identified; **five are done and merged into `main`**
(#1/#3/#5/#6 via [PR #47](https://github.com/aiAdrian/flatland_ui/pull/47),
#2 as a follow-up commit) — see §0.1 and §5:

1. ✅ **README clone command was dead** — pointed at
   `-b experiment/vibecoding-playground https://github.com/danib8005/…`
   (branch and fork both gone). Fixed to
   `git clone https://github.com/aiAdrian/flatland_ui.git`; stale
   "Playground branch" callout in `README.md` and the `PLAYGROUND.md` header
   de-staled to match.
2. ✅ **No CI** — fixed via `.github/workflows/ci.yml` (2026-09-05): two
   independent jobs, `ng build --configuration production` and `pytest` (with
   `requirements-dev.txt`), on push/PR to `main`. Deliberately left out:
   `ruff check` (1628 pre-existing findings — its own cleanup, not a gate to
   turn on blind) and `ng test` (needs a real/headless Chrome, not just a
   build). Along the way, fixed `README.md`'s "Node.js 20+" — Angular CLI 22
   actually needs ≥22.22.3 (the Dockerfile already knew this).
3. ✅ **torch gap in the quick start** — `requirements.txt` deliberately omits
   PyTorch; without it the Director silently degrades to the model-free
   fallback (`avoidance (no models)` instead of `search`, A/B/C strategy tiles
   without a forecast) with no error. README now calls this out explicitly and
   points at `requirements-dev.txt` (the same set the test suite needs).
4. **Licence convention** — this repo is Apache-2.0, `flatland-association`
   repos are consistently MIT. Needs alignment with them before the move, and
   contributor sign-off if it changes. **Owner: user, not started here.**
5. ✅ **Model checkpoints had no provenance** — `backend/models/goal_directed/
   {evaluator,connection}.ckpt` (3.4 MB) now have a `SOURCE.md` (mirroring
   `olten/SOURCE.md`'s pattern): sha256, loading class, origin commit
   (`a31ee7c`, 2026-08-03), training entry points, and an explicit note that
   the exact dataset cache / hyperparameters / validation scores behind the
   *shipped* weights are not recorded — the training commands reproduce *a*
   model of the same architecture, not these files byte-for-byte.
6. ✅ **13 untracked macOS/cloud-sync duplicate files** (`foo 2.ts` next to
   `foo.ts`, one with unresolved git conflict markers) — moved to the session
   scratchpad (not deleted; the tree is shared with parallel sessions), plus a
   commented `.gitignore` rule (`* 2.*`) so they stop reappearing in
   `git status`.

Not yet touched: **#4 (licence)** — needs the user's call with the Flatland
team; nothing here can settle it.

---

## 4. Open question — not yet decided

**`docs/reading/`, `docs/delegation/`, `docs/archive/` (17 files, 240 KB).**
`docs/reading/2026-08-16-flatland-oekosystem-recherche.md` originally named a
named third party's email address (a squashed-commit author on an upstream
repo, unrelated to this project) — since removed from that file and from a
second mention in `docs/plans/flatland-ecosystem-reuse-plan.md` — but it's the
concrete example of why this category needs a human decision before
publishing, not a default:

- **All three out** (leaning recommendation) — none of the 17 files serve a
  new contributor; `docs/reading/` is exactly the workshop/review-notes
  category that just needed a name pulled.
- **Only `docs/reading/` out**, `delegation/` and `archive/` kept as visible
  process trail.
- **All three kept** — full transparency on how the work got built, but then
  every file needs an individual pass for names and unpublished third-party
  detail before the branch is pushed.

## 5. Next steps

~~Merge `enabler` into `main`~~ (done, PR #47) and ~~build the CI
workflow~~ (done, §3.2) both landed directly on `main` rather than on a
separate `release/…` branch — by the time either happened, PR #46 had
already merged `explore_db` into `main` unreduced (§0.1), so there was no
clean `main` left to protect with a side branch. The remaining §1 drops are
being applied the same way, one at a time, as they get decided or verified
(the scene JSON duplicates are done; the HF workflow and `PLAYGROUND.md`
are not yet).

1. Decide §4.
2. Apply the rest of §1's drops directly on `main` (HF workflow,
   `PLAYGROUND.md`, and `docs/reading`/`delegation`/`archive` once §4 is
   decided).
3. Resolve §3.4 (licence) with the Flatland team before pushing history —
   `docs/reading/2026-08-16-flatland-oekosystem-recherche.md`'s email address
   is still present in three commits of the existing history
   (`259d10c`, `9292d08`, `da1e5d2`); decide whether the move carries full
   history, a filtered history, or a flat initial commit.
