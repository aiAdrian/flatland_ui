# Product Vision — Flatland Dispatcher Playground

> ⚠️ **The current version of the Product Vision lives in the wiki:**
> https://github.com/aiAdrian/flatland_ui/wiki/Product-Vision
>
> This file is a **mirror** of that page (state: 2026-08-21), kept in the repo so
> that plans and specs here can link to it. The wiki is authoritative — if the
> two differ, the wiki wins. To be refined with the team on Tuesday.
>
> Everything from "Product Vision" to "First steps" below is the wiki text
> verbatim. The two appendices after it are additions from this repo: a more
> detailed MVP proposal, and an inventory of what already exists.

---

# Productvision

## Vision

Human-AI Collaboration in control rooms becomes something you can explore, prototype, try and validate before you start building it for real.

Tagline: the future human ai enabled control room is explored before it is procured

(Older Vers 1) An open source platform to explore, experience and evaluate future human-ai teamwork in a simulated environment for network operations.

(Older Vers 2) Getting beyond mockups, slides or concepts in human-ai collaboration for control rooms by exploring and evaluating interactions with a simulated environment

(Older Vers 3) Anyone designing human-ai collaboration for critical infrastructure control rooms can prototype and validate their approach with people, MARL algorithms and a simulation.

### Target group - Who is the user of the solution?

Primary user groups:
* HMI, UX and Human Factors researchers who want to design, explore and research new forms of human-ai collaborations in control rooms and who currently mainly relay on mockups.
* MARL, RL, AI researchers who need to test and benchmark their algorithms inside a almost realistic human-in/on-the-loop setting and who currently mainly test algorithms against each other.

Secondary user group
* Developers of solutions prototyping human-ai collaboration to identify requirements for their own solutions.
* Interested domain experts and companies running railway networks to learn about the future of human-ai collaboration impacting their field and to specify future systems better

Also served:
* Teachers and students who need an accessible environment to learn about Human-AI collaboration in doing and not just with theory
* AI Policy and ethics experts to ground their guidelines and recommendations on validated insights on human-ai collaboration and not primarily on assumed technical capabilities and their impact on society

### Needs - What problems do we want to solve?

* Human-AI interaction concepts for control rooms can't be explored today beyond scripted demos or mockup. The solution allows people to create and evaluate human-ai interaction concepts.
* Algorithmic research and HMI research are often done independently in silos. An integrated solution allows to develop more realistic prototypes and therefore create and explore the potential of a future joint human-ai system. A simulation environment, benchmarks and questionnaires support comparable validations.
* No need to start from scratch and be ready to focus on the hard part: developing new forms of human-ai interactions in control rooms
* Simple showcases allow to make the future tangible and improve the conversation about the needs of a future new systems for control rooms.
* A library of validated interaction patterns grounded in human factors research in combination with algorithms from MARL domain becomes the basis for developing future operative systems for control rooms.

### Product - What is it?

A modular HMI, a set of MARL algorithms plus simulation playground, in which the way humans and AI share the work is a configurable variable, not a fixed design. A joint and proven set of evaluation criteria supports the assessment of the created solution and comparison with others.
* Adjustable autonomy, algorithms and interaction design as core element to run experiments
* Simulation environment that is configurable (infrastructure and scenarios)
* Catalog of widgets that can be arranged in an HMI interface. Extensible with own widgets
* Catalog of MARL algorithms that can be used to run the simulation. Extensible with own algorithms
* Catalog of infrastructure and scenarios.
* Designer for infrastructure, scenarios, HMI layouts, widgets for interaction patterns
* Configuration and execution of experiments including questionnaires, logfiles and benchmarks to assess the solution

Feasible today, on a laptop: Angular + FastAPI + Flatland, no cluster, no external services.

### Business Goals

Impact
* Produce evidence and better understanding how to design future human-ai collaboration in control rooms with a complementary approach.

Short term
* Run first experiments and foster the exchange between the first group of users

Long term
* Developing a interdisciplinary community as part of the flatland association
* Material for teaching purposes by flatland community members
* Funding for further development, community activities and goals of the platform through research funds or others.

# First steps

## MVPs

### MVP 1
One set up for one experiment from the beginning to the end.(German: Durchstich)
Set up can be used for a pilot study with expert users. Results can be used for research.

### MVP 2
A workshop/hackathon/community event with primary users to design their own experiments. Focus on one aspect (eg. algorithms or hmi)

---
---

# Appendix A — MVP proposal in detail

> Repo-side addition, not part of the wiki page. It keeps both MVPs exactly as
> defined above and only adds scope boundaries and acceptance criteria, so that
> "done" is decidable rather than arguable.

## MVP 1 — the Durchstich

> A dispatcher sits down, works through one realistic disruption in a given
> condition, and leaves behind a complete, analysable record — without a
> developer in the room.

**In scope**

1. One scenario family, reproducible: fixed seed, a disruption that reliably
   creates a decision moment, comparable difficulty across participants.
2. At least two conditions that are observably different in that scenario —
   otherwise there is nothing to compare and the pilot yields a description, not
   a result.
3. A guided session end to end — onboarding → run → reflection → survey — in
   30–45 minutes, self-explanatory enough that the facilitator only observes.
4. One session record per run, self-describing: participant and condition id,
   scenario config and seed, every decision with owner and decision time, mode
   and setting changes, reflection and survey answers.
5. A pilot with 3–5 expert users, and the data from it actually analysed.

**Done when**

- [ ] A run can be repeated with an identical situation for a different person.
- [ ] The conditions differ in what the operator sees and can do — visibly.
- [ ] One file per session contains everything needed to compare two sessions.
- [ ] A facilitator who is not a developer can run a session start to finish.
- [ ] Five sessions have been run with expert users **and the data has been read**.

The last box is the one that matters: reading the data is where you find out that
something decisive was never logged — and after the study is too late.

## MVP 2 — the community event

> Participants design and run their own experiment on the platform, on one axis
> (algorithm *or* HMI), and leave with something of their own that runs.

**What must be true before inviting people**

- **A documented seam per axis.** For the HMI axis: how a new widget is written
  and registered. For the algorithm axis: how a policy is implemented and
  registered. Both must be followable without reading our source.
- **A working example per axis** that a participant can copy and modify —
  the fastest form of documentation.
- **Time-boxed setup.** If getting the environment running takes longer than the
  first hour, the event is about installation, not about ideas.
- **A result they can take home**: their configuration, their session record,
  their KPI numbers.

**Done when**

- [ ] At least one group integrated something of their own through a seam,
      without changing our code.
- [ ] They ran their own condition and got a session record out.
- [ ] What they needed to know was in the documentation, not in our heads.
- [ ] Their record has the same shape as ours, so results are comparable.

## Out of scope for both

Voice agents and conversational actors · bus replacement and passenger
information · real network topology · multi-user or authenticated operation ·
central storage (a file per session is enough) · per-agent policy assignment.

---

# Appendix B — Where we stand today

> Inventory against the product bullets above, checked in the code on
> 2026-08-21. ✅ exists · ⚠️ partial · ❌ missing.

## Product claims

| Claim | State | Evidence / what is missing |
|---|---|---|
| **Adjustable autonomy, algorithms and interaction design as configurable variables** | ✅ | Three interaction modes switchable at runtime; three altitudes (KPI objective, policy, single-train override). The strongest and most distinctive part |
| **Simulation environment, configurable** | ✅ | Flatland with seeded generation, an Infrastructure Builder, an imported ECML 2026 scene, a fixed guided-demo environment |
| **Catalog of widgets, arrangeable in an HMI** | ✅ | 29 registered widgets (25 shipped, 4 first cut), a Layout Designer, a Widget Gallery |
| **…extensible with own widgets** | ⚠️ | A documented authoring process and a `create-widget` skill exist, but a new widget means writing a component and registering it in several seams — feasible for us, not yet for an outsider without help. **MVP 2 depends on this** |
| **Catalog of MARL algorithms** | ❌ | Six policies are registered: deadlock avoidance, shortest path, forward only, do nothing, random, and the goal-directed Director planner. **None of them is RL or MARL.** The seam is real and stable; the catalog behind it is not. Nearest fix: integrate the consortium implementations (PPO / IMPALA / DDDQN exist in the AI4REALNET repos) rather than writing our own |
| **…extensible with own algorithms** | ✅ | A `Policy` base class plus a registry; the same seam the Director planner uses. This is the part an algorithm researcher would meet, and it holds |
| **Catalog of infrastructure and scenarios** | ⚠️ | One scenario preset (ECML 2026 Scene 1), the guided-demo environment, procedural generation, and Builder scenes in browser storage. A *catalog* in the sense of a curated, shareable, versioned set does not exist yet |
| **Designer for infrastructure** | ✅ | Infrastructure Builder with validation and export |
| **Designer for HMI layouts** | ✅ | Layout Designer |
| **Designer for scenarios** | ⚠️ | Scenario parameters are configurable at session start; there is no designer for scripted event sequences. See `plans/scripted-events-plan.md` |
| **Designer for widgets / interaction patterns** | ❌ | Widgets are written in code. A designer for interaction patterns does not exist |
| **Experiments: questionnaires** | ⚠️ | Three validated instruments are implemented (NASA-TLX, Trust in Automation, UEQ-S), config-driven per mode — **but the answers only live in browser storage and cannot be exported** |
| **Experiments: logfiles** | ⚠️ | A decision log with sequence, timestamp, sim step, mode, accountability owner, decision time and rationale, plus a JSON export — but no session header, no participant id, and a silent 500-entry cap |
| **Experiments: benchmarks** | ⚠️ | KPIs per scenario exist, and the Director planner has its own evaluation set, ground-truth verification and weight sweep. There is no benchmark runner across conditions or participants |
| **Runs on a laptop** | ✅ | Verified 2026-08-21: backend and frontend start, a session runs, the Director planner computes live |

## What this means for the two MVPs

**MVP 1 is close.** Simulation, modes, conditions, instruments and the decision
log all exist. The gap is a narrow one and it is the same gap in three places:
**the record cannot be collected.** Survey answers, reflection answers and the
decision log live in three separate browser-storage namespaces with no common
header and no joint export. Closing that (`plans/interaction-logging-plan.md`,
phases P1–P2) is the critical path to MVP 1 — plus two decisions that are not
technical: how the participant id gets in, and consent/anonymisation for
free-text answers.

**MVP 2 is further away than it looks, and on the axis one would not expect.**
The *algorithm* axis is in good shape: the policy seam is real, and a
participant could plausibly register their own policy in a day. The *HMI* axis is
the harder one — adding a widget touches several registration points and is
currently tribal knowledge. And the "catalog of MARL algorithms" that the
algorithm-facing audience is being invited for is empty. Before a community
event, those two are the work: **an outsider-followable widget seam, and at least
one real learned policy in the catalog.**

## Two claims to keep honest

The vision names "MARL algorithms" three times, and today there are none in the
platform. That is fixable by integration and it is on the roadmap — but it should
be stated as a direction, not as an inventory, in any material shown to the AI
research audience. They will check.

Likewise "a library of validated interaction patterns": the *library* exists (a
widget catalog with per-mode behaviour and grounding), the **validation does
not** — no study has yet produced the evidence that would make a pattern
"validated". That is precisely what MVP 1 is for, which is a good story: the
vision names the destination, and the first MVP is the first step of it.
