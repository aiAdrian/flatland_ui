# Widget spec — Trains (v2 · Dispositionstabelle)

> Variant of the shipped **Trains** widget (`agents`), not a new role. Follows
> [`widget-variants-versioning.md`](widget-variants-versioning.md): same `role`,
> new `type`, both selectable side by side.
>
> Origin: the HMI review of 2026-08-22
> ([`docs/reading/2026-08-22-hmi-review-workshop.md`](../reading/2026-08-22-hmi-review-workshop.md) §1).

## 1. Identity

- **Name:** Trains (Dispositionstabelle)
- **`kind`:** `context` — same as its v1 sibling. The row *explains and scopes*
  one train's situation; the buttons in the row are the drill-down action, exactly
  as in the v1 roster. (Deliberately **not** `control`: classifying a variant
  differently from its own role would split the gallery taxonomy.)
- **`granularity`:** `overview-detail` — the table is the overview; each row
  carries its own detail (Meldung, nächste Weiche) and its own actions, which is
  the whole point of the redesign.
- **Default zone:** `bottom` (wide). v1 keeps `left`.
- **Panel `type`:** `agents-table` · **`role`:** `agents` ·
  **`variantLabel`:** `v2 · Dispositionstabelle`
- **Catalog id:** none — this is not one of the A–D AI-novel widgets
  ([`widget-catalog.md`](widget-catalog.md)); it is an information-architecture
  variant of a shipped widget.
- **Source(s):** HMI review 2026-08-22 (SBB, Gaby) — the sketch on board page 2.
- **Grounding reference:** the **redesigned SBB Tunnelautomatik** as reported in
  the review: infrastructure in the upper third, a per-train table with the
  Handlungsaufforderung below. That is a real control-room layout that replaced a
  left/right split with the same complaint we have ("der Nutzer muss viel
  suchen"). Supporting: the disposition-table convention in rail control rooms.
- **Source origin:** `Source: from-scratch, deliberately.` No consortium
  implementation is being reimplemented here — this is presentation/HMI framing,
  which CLAUDE.md §Reuse keeps ours. **No algorithm is involved**: the table
  renders store data that already exists (`agents`, `impact`, `notifications`)
  and acts through the shared dispatch seam (`TrainActionService`), like every
  other affordance.
  See §8 for why that is not a "reinvented wheel".

## 2. Promise

> The operator sees every train's situation **and its available action in the
> same row**, so deciding no longer means reading the left column, the map and
> the right column and holding a train number in your head across all three.

## 3. Per-mode behaviour

Availability is inherited from the role — a variant must not silently change it
(`agents` is withdrawn in Director because a per-train table is dispatcher-level
detail while Director supervises objectives).

- **Recommendation (WP 3.1) — offered.** Framing follows
  `store.optionPresentation() === 'recommended'`: the row marks which action the
  AI's current plan implies, and an action the operator has already set shows as
  their standing override (toggle, click again to clear). Same semantics as v1,
  now visible in the row instead of two columns apart.
- **Co-Learning (WP 3.3) — offered.** `optionPresentation() === 'neutral'`: the
  actions are rendered as **equal choices**, with no AI-preferred marking — the
  operator formulates their own action first. The override the operator sets is
  still marked as theirs (that is their own state, not an AI preference), and
  still flows into `coLearningFeedback` via the unchanged store path behind the
  dispatch seam.
- **Director (WP 3.4) — not offered** (`null`), like v1. Re-enabling is a config
  flip in `panel-mode-availability.ts` if the study later wants it.

## 4. System interaction

**Data in** — everything already in the store, no new endpoint:

| Signal | Used for |
|---|---|
| `store.agents()` → `AgentDTO` | Status, Zug, Soll-Ank./Puffer, Störung, `next_decision`, `override_action` |
| `store.impact()` → `ImpactItem` | the Meldung column's "blockiert durch Zug N, erreicht in X, frei in Y" |
| `store.notifications()` | per-train event text where one exists |
| `store.optionPresentation()` | the per-mode framing of the action cell |
| `AgentColorService` | the train's colour dot — same identity as map, list and Marey |

**Actions out:** `TrainActionService.toggle(handle, action, 'table')` — the
dispatch seam every affordance now goes through
(`core/dispatch/train-action.service.ts`). The table adds a new **origin**, not
a new action path, so its decisions land in the same decision log as a
roster- or map-issued one and carry `origin: 'table'`. `store.selectedHandles`
on row click (drill-down to Agent Inspector).

**`writes`:** `simulation` — declared in the catalog like every other widget
(interaction-framework.md §3).

**Backend table:**

| Field / capability | Available now | To build (flagged) |
|---|:---:|:---:|
| Status, Zug, Soll-Ankunft, Puffer, Störungsrestdauer | ✓ | |
| `next_decision` + options (the action cell) | ✓ | |
| Blocked-by / clears-in (Meldung column) | ✓ (`impact`) | |
| Per-train notification text | ✓ | |
| **Remaining steps to the next decision point** (Gaby's "Remaining Steps" read literally) | | ✓ flagged — the DTO carries `malfunction_remaining` and `time_to_deadline`, not "steps until the switch". Shown as malfunction-remaining where it applies, otherwise the deadline slack; a true steps-to-decision-point field would be a backend addition. **Not faked.** |
| Per-agent policy | | ✗ out of scope — policy is global per session (CLAUDE.md guardrail) |

## 5. Allocation & accountability touchpoints

- **Loop stage:** context → decision (the row is where the decision is taken).
- **Owner per mode (`allocation`):** Recommendation → shared (AI proposes, human
  disposes) · Co-Learning → human (AI offers no preferred option) · Director →
  not offered.
- **Decision events emitted:** none new. The dispatch seam records the override
  with `accountableOwner`, `origin`, the AI suggestion at that moment, sim step
  and mode, and raises `pendingRationale` where the mode asks for a "why?".
  Because the table reuses that call, every decision taken in a row lands in the
  same audit trail as one taken in the roster — which is the point of not
  building a parallel action path.

## 6. Acceptance scenario

A train malfunctions and blocks another. The operator, working only in the
table: sorts/filters to the conflict, reads in **one row** that Train 7 is
malfunctioning, is 105 steps past its latest arrival, blocks Train 2, and that
its next switch is at (9,28) — then clicks `Hold` in that same row. The Agent
Inspector and map follow the selection; the override appears in the decision log
with the same fields as a roster-issued one.

**Measurable success criterion (Q4 allocation / Q5 study value):** for the
disruption task, the number of distinct screen regions the operator must visit
to go from "notice" to "act" drops from **3** (Notifications → Agents list →
map/Impact) to **1**. Countable from the interaction log (region of each
interaction event between a notification and the resulting override) and
observable in the next walkthrough with Gaby.

## 7. Effort & changes

- **Effort:** M (150–400k tok / 1–3d).
- **Files / seams:**
  - new `frontend/src/app/features/agents-table/agents-table.component.{ts,html,scss}`
  - `panel-plugin-host.component.ts` (import) + `.html` (`@case 'agents-table'`)
  - `layout-designer.component.ts` palette entry
  - `core/layout/panel-mode-availability.ts` — `['recommendation', 'co-learning']`,
    identical to `agents`
  - `core/widgets/widget-catalog.ts` — new entry + add `role`/`variantLabel`/
    `variantDefault` to the existing `agents` entry
  - `docs/reference/panel-mode-matrix.md` — row
  - no backend change

## 8. Open questions / risks

- **Is this a reinvented wheel?** No algorithm is involved — it is a layout for
  data the app already has, calling the existing override seam. CLAUDE.md's
  reuse rule binds algorithms (UQ, calibration, policy negotiation); presentation
  framing stays ours. Recorded here explicitly rather than by omission.
- **"Remaining Steps" is ambiguous** in the sketch (it matches the malfunction
  countdown in her example). Shipping it as malfunction-remaining / deadline
  slack and flagging the true steps-to-decision-point as a backend extension —
  worth one question to Gaby at the next walkthrough.
- **Two variants, one role, no switcher yet.** Step 2 of
  `widget-variants-versioning.md` (a variant switcher in the palette) does not
  exist; today choosing v2 means placing it in a layout. Acceptable — that is
  exactly how `recommendations-classic` ships.
- **Wide zone assumption.** The table needs horizontal room; in a narrow column
  it must scroll inside itself rather than push the layout. Non-negotiable
  acceptance detail, not a "nice to have".
- **Does the table replace the roster for the study, or compete with it?**
  Deliberately left open: having both selectable is what lets the next
  walkthrough compare them instead of arguing about them.
