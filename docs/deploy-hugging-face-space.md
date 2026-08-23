# Deploying to a Hugging Face Docker Space

Two branches carry the Space setup, one per demo:

| branch | base | Space |
|---|---|---|
| `hf-space-explore-db` | `explore_db` | the working playground |
| `hf-space-main` | `main` | the merged baseline |

Each is its base branch plus the two things a Space needs: the YAML front
matter at the top of `README.md` (which is why this is a branch — GitHub
renders that block badly), and a `Dockerfile` that runs as UID 1000. Everything
else (same-origin SPA serving, `${PORT:-8000}`) already worked. Keep the two
branches rebased on their bases rather than merging between them.

## Push it

One HF Space per branch, each pushed to that Space's `main`:

```bash
git remote add space-explore-db https://huggingface.co/spaces/<user>/flatland-dispatcher-explore-db
git remote add space-main       https://huggingface.co/spaces/<user>/flatland-dispatcher-main

git push space-explore-db hf-space-explore-db:main
git push space-main       hf-space-main:main
```

Spaces authenticate with a write token (`huggingface-cli login`, or a token in
the push URL). Create the Spaces first on huggingface.co with SDK *Docker* —
the front matter then only has to match what is already there.

HF builds the root `Dockerfile` on every push; `app_port: 8000` in the README
front matter points the proxy at uvicorn. No environment variables are needed —
`CORS_ORIGINS` only matters when frontend and backend live on different origins,
which they do not here. Build logs are on the Space's *Logs → Build* tab; the
default startup timeout is 30 minutes, which the Angular build plus the
`flatland-rl` install fit into comfortably.

> Not verified locally: this machine has no Docker daemon, so the image was
> never built end to end. The paths were checked by hand (`angular.json`
> `outputPath: dist/frontend` → the application builder writes
> `dist/frontend/browser`, which is what the Dockerfile copies).

## Why the free hardware actually matters here

| | Render Free | Render Starter | HF CPU Basic | HF CPU Upgrade |
|---|---|---|---|---|
| CPU | 0.1 vCPU | 0.5 vCPU | 2 vCPU | 8 vCPU |
| RAM | 512 MB | 512 MB | 16 GB | 32 GB |
| Price | free, 750 h/mo | $7/mo | free hardware¹ | $0.03/h |
| Idle | spin-down after 15 min | — | sleeps after ~48 h | never (configurable) |

¹ CPU Basic has no hourly cost, but creating a Space that runs *compute*
(Docker or Gradio) requires a paid account plan. Static Spaces are free.

### Measured on one core (2026-08-23, dev MacBook, `OMP_NUM_THREADS=1`, `explore_db`)

The play loop in `backend/app/api/websockets.py` runs `act_many` → `env.step` →
`serialize_env` → broadcast synchronously on the event loop, so one step costs
the sum of the three:

| scenario | act_many | env.step | serialize | per step | ceiling |
|---|---|---|---|---|---|
| 3 agents, 50×20 (UI default) | 0.4 ms | 0.2 ms | 2.9 ms | 3.5 ms | ~287 steps/s |
| 15 agents, 80×40 (study size) | 9.4 ms | 1.2 ms | 9.2 ms | 19.9 ms | ~50 steps/s |
| ECML 2026 scene 1, 150×120 | 4.8 ms | 0.2 ms | 57.8 ms | 63.3 ms | ~16 steps/s |

Serialization, not the simulation, dominates on large grids. The what-if
endpoints are the other hot spot (cold = cache miss, warm = the hash cache in
`hmi.py` hitting):

| endpoint | study size | ECML scene 1 |
|---|---|---|
| `GET /hmi/scenarios` | 1254 ms cold, 40 ms warm, **9.1 MB** | 1188 ms cold, 28 ms warm, 3.4 MB |
| `GET /hmi/recommendations` | 1450 ms cold, 2 ms warm | 7 ms |
| `GET /hmi/marey-data` | 1 ms | 439 ms cold, 143 ms warm, 473 KB |

Peak RSS, same run: 111 MB after import, ~31 MB per stepped session, and
**662 MB** with four study-size sessions after their what-if rollouts.

### What that implies

- **512 MB (Render Free) is below the working set.** Four concurrent sessions
  already peak at 662 MB — that is an OOM restart, not a slow request.
- **0.1 vCPU multiplies every number above by roughly ten.** A study-size step
  lands near 200 ms, so the loop tops out around 5 steps/s while the UI speed
  control asks for up to 20; `/hmi/scenarios` goes from ~1.3 s to somewhere past
  10 s, during which the play loop is blocked, because it is the same thread.
- A dev-machine core is faster than a cloud vCPU, so treat the table as an upper
  bound — the *ratio* between the tiers is the point, not the absolute ms.
- **Stay at one uvicorn worker.** Sessions live in `SessionManager._sessions`
  in-process; a second worker would answer requests for sessions it does not
  hold. 2 vCPU therefore buys headroom for one session at a time plus the
  rollouts, not parallel participants. For a study with concurrent participants,
  give each their own Space (or upgrade and accept the GIL).

## Persistence

Disk is wiped on every Space restart, and HF's old persistent-storage feature is
gone — the replacement is an attached Storage Bucket (paid, mounted at `/data`
at runtime only). The Dockerfile makes `/app/data` writable so
`operator_model.py`'s carry-over profiles work within a container's lifetime,
but they do not survive a rebuild.

For study data that must outlive the container, the idiomatic Spaces answer is
to write into a Dataset repo with `huggingface_hub` (scheduled uploads). That
also fits the D3.1 norm of a "structured, traceable decision record" better than
a JSON file in a container.

## Before sharing the link

The app has no authentication. A public Space means anyone can create sessions
and run rollouts on the same single-worker process. Either keep the Space
private, or accept that the CPU is shared with whoever finds it.
