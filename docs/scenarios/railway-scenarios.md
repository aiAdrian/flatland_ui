# Railway scenarios — AI4REALNET resource (simplified)

Working reference for our cases, distilled from the official AI4REALNET
deliverables:
- **D1.1** — Framework and use cases (use-case framing, objectives)
- **D4.1** — Evaluation and test protocols (the operational scenarios + KPIs)

(Both are SBB/consortium-authored — this is our own consortium material.)

---

## The two railway use cases (D1.1)

| Use case | Objective | Human–AI relationship |
|---|---|---|
| **UC1.Railway — Automated re-scheduling** | AI detects the need to intervene, decides, and executes the intervention. | AI acts autonomously; **human supervises** and can switch the AI off / take control. |
| **UC2.Railway — AI-assisted human re-scheduling** | AI assists the dispatcher: derives dispatching options on disruptions/delays, presents them in near real-time. | **Human decides**; AI suggests, manages alert frequency, allows override. |

> Re-scheduling = change the **order** of trains; **re-routing** = pick other
> routes. These are the core remedial actions across all scenarios.

### Maps onto our three modes
- **UC1.Railway (autonomous + supervise)** → our **Director** mode
- **UC2.Railway (AI suggests, human decides)** → our **Recommendation** mode
- **UC2.Railway + co-learning (mutual learning)** → our **Co-Learning** mode

---

## Operational scenarios (D4.1)

Seven railway operational scenarios. Each has a common 6–8 step flow:
*normal → disruption detected (AI and/or human) → AI assesses impact → AI
generates revised schedule/routing → human evaluates/validates/decides →
continuous monitoring → services resume with minimal delay.*

| ID | Scenario | Trigger / situation | Instances | Our mode |
|---|---|---|---|---|
| **UC1.R-1-004** | Re-scheduling at infrastructure malfunction | Track blockage, switch failure, overhead-power or signal breakdown | Track Blockage · Signal Failure · Overhead Power Failure | Director (autonomous, human monitors) |
| **UC1.R-2-005** | Emergency response to adverse weather | Snow/flood/storm closes track or power line | Heavy Snowfall · Flooding · Storm Disruptions | Director |
| **UC1.R-3-006** | Partial closure of a large station | One/more station tracks closed (emergency/security); large long-term impact | Emergency Closure · Infrastructure Failure · Passenger Overload | Director (AI solves as independently as possible) |
| **UC2.R-1-007** | Reactive re-scheduling | Adapt schedule **after** a disruption already happened | Train Breakdown · Signal Malfunction · Sudden Passenger Demand | Recommendation |
| **UC2.R-2-008** | Co-learning for reactive re-scheduling | Same as above, **+ feedback loop**: human overrides refine AI; AI supports human learning | AI-Dispatcher Collaboration · Pattern Recognition · Decision Alignment · Human Learning | Co-Learning |
| **UC2.R-3-009** | Proactive re-scheduling | Act on **weak signals** (slight delays → future conflicts) **before** disruption | Weather-Based · Passenger-Flow · Human Expertise | Recommendation (anticipatory) |
| **UC2.R-4-010** | Co-learning for proactive re-scheduling | Proactive + mutual learning; AI refines predictive models from dispatcher feedback | (mutual learning) | Co-Learning |

---

## What we can run today vs. needs extension

| Situation | In our Flatland app today | Note |
|---|---|---|
| Train/infrastructure **malfunction** (UC1.R-1, UC2.R-1) | ✅ yes — Flatland malfunctions; respond via reroute (override at switch), hold (STOP), policy switch | closest match to our current capability |
| **Reactive re-scheduling/re-routing** | ✅ partial — reorder/reroute via overrides + policy switch | no explicit "swap train order" action; done via routing |
| **Co-learning** (UC2.R-2/4) | ◑ human side built (neutral options, reflection, intervention log); AI-learns-from-human open | see co-learning-direction.md |
| **Proactive** (weak signals, UC2.R-3/4) | ◑ forecasts/what-if exist; explicit weak-signal detection not yet | |
| **Weather / station closure / passenger demand** | ⚠️ not modelled — Flatland has no weather, closures, or passenger load | needs custom scenarios + richer action/disruption model |

---

## Malfunction / disruption variants

The deliverables give **two complementary taxonomies** — keep them apart:

### A. Operational disruptions (what the dispatcher sees — D1.1 / D4.1 scenarios)
From the scenario descriptions and their instances:
- **Infrastructure malfunction**: track blockage (fallen tree/debris), **switch
  failure**, **signal breakdown**, **overhead-power failure**
- **Train breakdown** (mechanical failure, train stops)
- **Weather**: heavy snowfall, flooding, storm (→ blocked track, power loss,
  reduced visibility)
- **Station closure**: emergency/security closure of one/more tracks
- **Demand**: sudden passenger surge / overload

These are the human-facing "what happened" types — candidates for a
malfunction-type label in the UI.

### B. Technical perturbation types (how it's modelled in Flatland — D4.1 §perturbation agent, Fig. 18)
The railway **perturbation agent** corrupts the AI's input state in **four ways**,
each with a concrete Flatland state manipulation (useful if we implement richer
disruptions ourselves):

| Perturbation | Meaning | How it's modelled in Flatland |
|---|---|---|
| **Track availability** | track/switch unavailable or misreported | **remove the transition** from the transition map (topology change) |
| **Track occupancy** | broken occupancy sensor | **remove** a train's position from state, or **inject a virtual non-moving train** on a segment |
| **Train location** | delayed/low-accuracy position report | **shift** the train's grid position (back, or to a connected segment) |
| **Train schedule** | corrupt schedule data | **change** the train's target station(s) and earliest-departure / latest-arrival times |

Lifecycle: perturbations are **added with prob. pₖ and removed with prob. qₖ**
(Poisson) → they appear and self-resolve over time (mimicking maintenance) — i.e.
they have a natural duration, like Flatland's built-in malfunction counter.

> **For us:** Flatland's built-in malfunction = a train stuck for N steps (our
> current capability). The richer variants above are not built-in but are
> **modellable** via these state manipulations — e.g. "track blockage" = remove a
> transition; "schedule disruption" = change target/times. This is the concrete
> recipe for a malfunction-type extension (ties to the custom-scenario work).

## KPIs relevant to our cases (selected, D4.1)

- **KPI-PF-026 Punctuality**, **KPI-RF-027 / KPI-DF-016 Delay reduction**
- **KPI-SS-032 System efficiency**, **KPI-NF-024 Network utilization**,
  **KPI-NF-045 Network impact propagation**
- **KPI-TS-035 Total decision time**, **KPI-AF-029 AI response time**,
  **KPI-AF-008 Assistant alert accuracy**
- **KPI-AS-068 Assistant adaptation to user preferences** (← our Level-B / operator model)
- **KPI-RT-058 Impact of partial human intervention on AI decisions**
- Human-user metrics: **Workload**, situation awareness, trust, AI co-learning
  capability, human control & autonomy (→ our survey track)

> Our **goal-achievement panel** already tracks arrived %, mean delay, on-time %,
> malfunctions — a practical subset of punctuality / delay / efficiency.

---

## How to use this for our cases

1. Pick a scenario family per study run: **malfunction (UC1.R-1)** is the most
   faithful to our current engine — start there.
2. Run the **same scenario** in all three modes (Recommendation / Co-Learning /
   Director) to expose the interaction difference (see mode-guide.md).
3. Measure with the KPI subset above + the post-session survey.
4. For weather / station-closure / proactive weak-signal cases: needs the
   custom-scenario + richer-disruption extension (noted in our backlog).
