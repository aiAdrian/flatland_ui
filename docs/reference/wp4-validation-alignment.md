# WP4 validation alignment — what we found, and what to check again at WP 4.3

> **Purpose of this doc:** a standing reminder. We are not integrating with
> WP4's validation infrastructure now, but we deliberately name our own
> schemas (decision log, reflection, trust signals) so that adapting to a
> real WP 4.3 validation campaign later is a **rename/mapping**, not a
> redesign. This doc is the "don't forget" note for that future point —
> re-check it whenever WP 4.3 requirements actually land, since the org's
> repos may have moved on by then.
>
> Found 2026-07-04 by directly querying the AI4REALNET GitHub org (see
> "How this was found" at the bottom for the exact commands, so a future
> session can re-verify rather than trust this document blindly — repos
> change).

## 1. What exists: the Validation Campaign Hub ("FAB")

[`AI4REALNET/ai4realnet-orchestrators`](https://github.com/AI4REALNET/ai4realnet-orchestrators)
is the consortium's own WP4 validation infrastructure: domain-specific
orchestrators that run submitted agents/policies against benchmark scenarios
and upload results (via `fab-clientlib`) to a central "Validation Campaign
Hub," internally nicknamed **FAB**.

**Three workflow types** (from the repo's own README):
- **offline-loop** — results uploaded manually as JSON (via FAB UI or REST API).
- **closed-loop** — an algorithmic researcher starts an experiment from the
  hub; the orchestrator runs it unattended and uploads results automatically.
- **interactive-loop** — a **human factors researcher** starts the
  experiment; the orchestrator auto-uploads what it can, and the researcher
  **manually completes the submission** via the FAB UI or CLI (e.g. survey
  results) before closing it. **This is the workflow that matches our HMI** —
  we are not a benchmarked autonomous agent, we are a human-in-the-loop
  session.

## 2. There is already a Railway domain module

`ai4realnet_orchestrators/railway/` exists in that repo — our domain, not
just power-grid/ATM. It's mostly scaffolding: `orchestrator_definitions.py`
lists a large catalog of named WP4 KPIs for Railway, almost all still
commented out / unimplemented. Only three have any code, and even those are
`raise NotImplementedError()` stubs wiring Docker-based closed-loop
benchmarking of submitted agent policies (not human-interaction logging):
`KPI-AF-029` (AI Response time), `KPI-NF-045` (Network Impact Propagation),
`KPI-PF-026` (Punctuality).

**The human-factors KPIs have no code anywhere in the org.** They are
evidently meant to be gathered through the interactive-loop (survey /
manual FAB entry), which is exactly the layer `hmisurveys` (TU Delft) and
our own reflection/decision-log work already occupy.

## 3. The named KPI catalog for Railway (as found; verify again before use)

Source: comments in `ai4realnet_orchestrators/railway/orchestrator_definitions.py`,
citing an internal spreadsheet ("Overview tests for KPI on validation
campaign hub.xlsx", WP4). Full list found, grouped by relevance to us:

**Directly overlaps our accountability/trust work (A1/A2/D1):**
| KPI ID | Name |
|---|---|
| HS-003 | Human intervention frequency |
| SS-030 | Significance of human revisions |
| AS-005 | Agreement score |
| HS-023 | Human response time |
| AF-029 | AI Response time |
| DS-015 | Decision support satisfaction |
| TS-038 | Trust in AI solutions score |
| TS-039 | Trust towards the AI tool |
| HS-018 | Human control/autonomy over the process |
| PS-089 | Perceived decision novelty |
| AS-006 | AI co-learning capability |
| HS-021 | Human learning |
| CS-013 | Comprehensibility |
| AS-001 | Ability to anticipate |
| AS-009 | Assistant disturbance |
| IS-041 | Impact on workload |
| WS-040 | Workload |
| SS-031 | Situation awareness |
| CS-049 | Cognitive Performance & Stress |
| RS-091 | Reflection on operator trust |
| RS-092 | Reflection on operator agency |
| RS-093 | Reflection on operator de-skilling |
| RS-094 | Reflection on over-reliance |
| RS-095 | Reflection on additional training |
| RS-096 | Reflection on biases |
| PS-097 | Predicted long-term adoption |

**Algorithm-benchmarking KPIs (not our HMI's concern, listed for completeness):**
DF-016 Delay reduction efficiency, PF-026 Punctuality, NF-045 Network Impact
Propagation, AF-050/051 AI-Agent Scalability (Training/Testing), DF-052..057
+ DF-090 Domain shift (adaptation/generalization/detection/robustness/
success-rate/forgetting), RS-058 Robustness to operator input, DF-069 Drop-off
in reward, FF-070/SF-071/072/VF-073 perturbation robustness, RF-078/AF-074/
DF-075/RF-076/SF-077 reward-curve/degradation/restorative metrics.

## 4. Current alignment (what we already did, so this isn't purely aspirational)

- [tile-a2-decision-log.md](../plans/tile-a2-decision-log.md) §5b maps our
  decision-log fields onto HS-003, AS-005, HS-023 explicitly.
- Cross-references noted (not yet built): A1's reliance signal → TS-038/039;
  D1's allocation display → HS-018; the planned reflection module → RS-091..096.

## 5. What to actually do when WP 4.3 requirements land

1. **Re-run the discovery** — re-check `ai4realnet-orchestrators`'s `railway/`
   module; the scaffolding may have grown real implementations by then, and
   the KPI IDs above could have changed or gained a formal schema.
2. **Check whether a Flatland-specific "submission" format is expected**
   (the orchestrator runs a Docker image against scenarios and reads
   `normalized_reward`/`percentage_complete`-style fields — see
   `PLAYGROUND.md` in that repo for the SQL definitions actually used) —
   this is for benchmarked agents, likely **not** what a human-in-the-loop
   HMI session submits, but confirm rather than assume.
3. **Check whether our decision-log / reflection JSON export needs to become
   the actual FAB submission payload**, or whether a separate export
   transform is more appropriate — don't force our internal schema to be
   literally the wire format if that adds coupling for no benefit.
4. **Only then** write any orchestrator/FAB-facing integration code — this
   was explicitly out of scope when tile A2 was speced (2026-07-04); doing it
   without real WP 4.3 requirements in hand would be guessing at a moving
   target.

## How this was found (for re-verification)

```
curl -s "https://api.github.com/orgs/AI4REALNET/repos?per_page=100"
curl -s "https://raw.githubusercontent.com/AI4REALNET/ai4realnet-orchestrators/main/README.md"
curl -s "https://api.github.com/repos/AI4REALNET/ai4realnet-orchestrators/contents/ai4realnet_orchestrators/railway"
curl -s "https://raw.githubusercontent.com/AI4REALNET/ai4realnet-orchestrators/main/ai4realnet_orchestrators/railway/orchestrator_definitions.py"
```
No GitHub auth was needed (public repo, unauthenticated REST + raw content
access) — code search (`/search/code`) does need auth, so a future check on
`WP4`/`4.3` mentions across the whole org would need a token.
