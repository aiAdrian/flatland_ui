# Mode guide — the same task in all three modes

A short, practical walkthrough of how the **same situation** is handled
differently in the three human-AI collaboration modes. Use it to onboard
yourself, Adrian, or study participants.

Switch modes with the **Mode dropdown** in the header (the coloured dot shows the
active mode: blue = Recommendation, green = Co-Learning, orange = Director).

## The example task

> Run a session. As trains depart, **two trains head toward a conflict at a
> junction** — without intervention one route leads to extra delay or a deadlock.
> Goal: get all trains to arrive with as little delay as possible.

Common setup (any mode):
1. Header **☰ menu → Session Settings** → keep defaults (or set grid/agents) → Apply.
2. Start a session (the welcome screen **+ New Session**).
3. Pick the mode in the header dropdown.

Layout reminder: **left = situation** (situation summary, event feed, agents),
**middle = the map** (+ agent overlay when you select a train), **right =
intervention** (policies, recommendations, KPI options).

---

## 1. Recommendation (WP 3.1) — AI suggests, you decide

The AI actively **proposes a preferred solution**; you stay the decision-maker.

1. Step or Play until the **Event Feed** (left) flags the conflict.
2. On the right, the **AI Recommendation** card appears: a preferred policy with a
   **confidence** value and a **countdown**.
3. The **Policies** comparison shows alternatives **with badges** (Recommended /
   Avoid) and **ranked by your KPI priorities**.
4. You **Accept** the recommendation, or override the train yourself via the
   **agent overlay** on the map (select the train → action buttons).
5. Continue.

**Feel:** the AI points at "the best option". Fast, guided, decision support.

---

## 2. Co-Learning (WP 3.3) — neutral options, you decide & reflect

Same conflict, but the AI **does not push a favourite** — it supports your
learning.

1. Step/Play until the conflict appears.
2. The **AI Recommendation card is hidden**. The **Policies** are shown
   **neutrally**: no Recommended/Avoid badge, no score ranking — equal options.
3. You choose (switch policy, or override the train on the map). Every
   intervention is **logged** (see the "Interventions" counter in the footer).
4. **Pause** (or finish the episode): the **Co-Learning Reflection** panel appears
   on the right with
   - a **statistical recap** (mirroring): how often you intervened, despite an AI
     hint, arrived/total, total delay;
   - **Socratic prompts** (e.g. "You intervened 3 times — which signals made you
     step in?").
5. (Planned) Compare "what if I had chosen differently" on the Marey.

**Feel:** the AI is a neutral partner; you decide, then reflect and learn.

---

## 3. Director (WP 3.4) — you set the goal, the AI runs it

You act as **director**: set a high-level directive up front, then supervise.

1. Switch to Director. The simulation **does not auto-start**; a **Director
   directive** card appears in the middle.
2. Set your **directive**: KPI priorities (right, "Options") and the **policy**
   (toolbar). The card summarises your current directive.
3. Click **Start autonomous run**. The **"AI in control"** banner appears; the AI
   dispatches all trains on its own.
4. You supervise via the **Goal Achievement** panel (right): live KPIs vs targets
   (arrived %, mean delay ≤ target, no malfunctions, on-time %) — green = met.
5. You only step in if needed: **re-weight KPIs**, **swap policy**, or **take over
   a single train** (agent overlay). Each counts as an intervention. **Pause** →
   "Resume autonomous run".

**Feel:** no per-incident prompts; you steer goals, the AI executes; intervene by
exception (adjustable autonomy).

---

## At a glance

| | Recommendation (3.1) | Co-Learning (3.3) | Director (3.4) |
|---|---|---|---|
| AI role | suggests a best option | offers neutral options | acts autonomously |
| Who drives | you, step by step | you, + reflection | the AI; you supervise |
| Recommendation card | shown (confidence, countdown) | hidden | hidden |
| Policies framing | badges + KPI ranking | neutral, unranked | neutral |
| Primary surface | recommendation + policies | options + reflection | goal-achievement panel |
| Start | manual step/play | manual step/play | directive → start autonomous |
| Human action | accept / override | choose / override (logged) | re-weight / swap / take over |

## Tips for a clear demo

- Use the **same scenario/seed** across the three modes so the difference is the
  *interaction*, not the situation.
- Watch the **right column**: it visibly changes per mode (recommendation card →
  neutral options → goal-achievement).
- In Co-Learning, **pause** to trigger reflection; in Director, note you must
  **start the run yourself** after setting the directive.
- After each run, open the **Post-session survey** (footer button at episode end)
  — the questionnaire adapts to the mode.
