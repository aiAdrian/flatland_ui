# Mode-scoped Layouts — Managing per-mode layouts with the Layout Designer

> **Status:** Draft for feedback (no implementation yet)
> **Context:** The three interaction modes (`recommendation` / `co-learning` /
> `director`) need different HMI layouts — e.g. Co-Learning surfaces a
> reflection panel in the centre, Director a goal-achievement dashboard. Today
> the Layout Designer produces a single global layout with no relation to the
> mode, and the saved-layout runtime path bypasses mode behaviour entirely.
> This plan makes layouts **mode-aware** and manageable from the designer.
> Frontend-only; respects the CLAUDE.md guardrail "gate presentation in the
> frontend, don't reshape payloads."

---

## 1. Problem (verified in code)

Two facts in the current implementation force the design:

1. **`FlatlandDesign` has no mode field.** Designs live in `localStorage`
   (`flatland.designer.designs.v1`), one is chosen manually via the welcome
   dropdown (`selectedRuntimeLayoutId`), with no link to
   `SessionStore.interactionMode`.
2. **The saved-layout runtime path ignores mode behaviour.** In
   `app.component.html`, `@if (useSavedRuntimeLayout())` renders columns/panels
   generically through `panel-shell`. Only the hardcoded `@else` (`three-col`)
   branch contains the mode-specific surfaces — reflection in the centre
   (`isCoLearning`), the goal dashboard (`aiInControl`), recommendations gating
   (`optionPresentation`). So the moment a designer layout is active, **none of
   the mode-specific behaviour renders**, and reflection isn't even placeable
   (`co-learning-reflection` is missing from the designer palette /
   `panel-plugin-host`).

**Consequence:** designer layouts and mode behaviour are mutually exclusive
today. The strategy must reconcile them.

---

## 2. Core idea — the layout *is* the gating

Rather than runtime per-panel gating, give **each mode its own design**;
switching mode selects the matching layout. A "base" layout is the shared
fallback, and the hardcoded system layout is the ultimate anchor so nothing is
ever lost during partial adoption.

---

## 3. Data model (minimal extension)

```ts
interface FlatlandDesign {
  …
  mode?: InteractionMode | 'all';   // NEW: which mode this design serves
  setId?: string;                    // NEW (optional): membership in a "layout set"
}
```

- `mode: 'all'` = universal; `mode: 'director'` = Director only; absent ⇒ `'all'`
  (backwards compatible with existing designs).
- `setId` bundles up to three mode-layouts into **one named set** (e.g.
  "Study A"). A set is the right abstraction for studies: activate a *set*, not
  three individual layouts.

---

## 4. Runtime resolver (pure function, explicit fallback chain)

Replace the single global `selectedRuntimeLayoutId` render decision with a
resolver reacting to `interactionMode()`:

```
resolveLayout(mode, activeSetId):
  1. design where setId == activeSetId && mode == currentMode   ← mode-specific
  2. design where setId == activeSetId && mode == 'all'         ← set base
  3. the explicitly selected single design (today's behaviour)  ← manual pick
  4. hardcoded system layout (three-col, carries mode logic)    ← always safe
```

- **Partial adoption works:** design only the Director layout, everything else
  falls through to the system default.
- Mode switch in the header reactively re-resolves the layout (an `effect` or
  `computed` on `interactionMode()` + active set).

---

## 5. Make the mode surfaces placeable

For layouts to replace runtime gating, the mode-typical panels must be in the
palette + `panel-plugin-host`:

- **Add `co-learning-reflection`** as a panel type (palette entry +
  `@case` in `panel-plugin-host`) — missing today.
- `goal-achievement` already exists; make a clear "Recommendations" tile too.
- **Defence-in-depth:** an optional `visibleInModes?: InteractionMode[]` per
  panel so a panel dropped into the wrong mode's layout hides itself. Primary
  mechanism stays "one layout per mode"; this is just a safety net.

---

## 6. Designer UX

- **Mode tag** at the top of the designer: "This layout applies to:
  ⟨Recommendation | Co-Learning | Director | All⟩", shown in the design list.
- **"Duplicate for mode"**: clone the current layout as the starting point for
  another mode (the three modes share ~80 % of the layout — don't start from
  scratch).
- **Set view**: a set shows its 1–3 mode variants side by side; "Set active"
  arms the whole set at once.

---

## 7. Phased rollout

- **P1** — `mode` field + resolver (steps 1, 3, 4) + reactive mode switch.
  Smallest useful unit; solves the core. Mode switch auto-picks the right
  layout, and the system layout as last step means nothing breaks while not all
  modes are covered.
- **P2** — `co-learning-reflection` placeable + `visibleInModes` safety net.
- **P3** — `setId` + set UX + "duplicate for mode" (study convenience).

---

## 8. Guardrails

- Frontend-only; presentation/layout selection only, no payload/trajectory
  changes. Do not touch `_recordTrajectory` or the scenario-refresh throttling.
- Keep `InteractionMode` as the single mode flag (no parallel flags).
- Existing designs (no `mode`) must keep working ⇒ treat missing `mode` as
  `'all'`, missing `setId` as "not in a set".
- Storage stays in `localStorage` under the existing designer keys; extend the
  schema, don't fork it.

---

## 9. Open questions (for feedback)

1. **Sets vs. loose tagging** — is the "layout set" abstraction (P3) worth it,
   or is per-mode tagging (P1) enough for the studies?
2. **Auto-switch vs. explicit** — should switching mode *always* re-resolve the
   layout, or should there be a "lock layout across modes" toggle for
   comparison scenarios?
3. **Partial sets** — if a set defines only Director, should the other modes
   fall to the set base, the manual pick, or the system layout? (Draft: set
   base → system layout.)
4. **System layout as a design** — should we eventually express the hardcoded
   `three-col` as a seeded, read-only design so *everything* goes through the
   resolver (one code path), instead of the current `@if/@else` split?
