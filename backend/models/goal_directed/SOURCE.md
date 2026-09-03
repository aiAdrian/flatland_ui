# Director models — source, training and licence

The two checkpoints the Director's `search` plan source needs. They are **not**
third-party artefacts: both were trained by this repository's own code, on data
this repository generates, and both are loadable with the pinned
`flatland-rl==4.2.6` and `torch>=2.2.0`.

| File | Bytes | Loaded by | Class |
|---|---:|---|---|
| `evaluator.ckpt` | 611 459 | `goal_directed_policy._load_models()` | `goal_based_policies.evaluator.ScheduleEvaluator` |
| `connection.ckpt` | 2 809 397 | `goal_directed_policy._load_models()` | `goal_based_policies.connection_model.ConnectionTransformer` |

```
sha256  evaluator.ckpt   4ca22a782738270dd0222910fa9a1a1ef7428124c035d48b2d3f5dfef3f6846c
sha256  connection.ckpt  008a8a83f0f61892ce8aeff1bc4f920858ee2785888c4c38c4b788b0677e6dfe
```

Both are PyTorch `torch.save` archives (zip containers rooted at `evaluator/`
and `connection/` respectively).

## Where they came from

Committed in `a31ee7c` (2026-08-03, **umbra99**) as part of *"First
implementation for the Director mode"*.

## What they were trained on

Simulated Flatland rollouts produced inside this repo — **no external or
licensed dataset is involved**, which is what makes these weights
redistributable with the code:

- **`evaluator.ckpt`** — supervised on measured outcomes from actually running
  each schedule in Flatland (`goal_based_policies/rollout.py:run_schedules`).
  Binary cross-entropy for "all trains arrived", plus an ordinal cross-entropy
  over six ordered delay buckets.
- **`connection.ckpt`** — one training example per planned transfer, labelled
  by whether it survived the rollout
  (`goal_based_policies/connections.py:evaluate_connections`). Scored per
  connection (accuracy, ROC AUC) and per scenario (MAE of the kept-ratio).

## Reproducing them

The training entry points ship with the code:

```bash
python -m app.policies.goal_based_policies.train_evaluator \
    --dataset-cache data.npz --block-epochs 50 --out schedule_evaluator.pt

python -m app.policies.goal_based_policies.train_connection_model \
    --dataset-cache data.npz --block-epochs 25 --out connection_model.pt
```

Training runs in resumable blocks and continues while the validation score
improves; rerunning the same command picks up from the checkpoint next to
`--out`.

> ⚠ **Not recorded for the shipped weights:** the dataset cache they were
> trained from, the hyperparameters actually used, and their validation scores.
> The commands above reproduce *a* model of the same architecture, not these
> exact files byte-for-byte. If the weights are ever retrained, record the run
> here — a checkpoint whose numbers nobody can state is a checkpoint nobody can
> defend in a study.

## Licence

Produced entirely by this repository's code from self-generated simulation
data, so they carry the repository's own terms — see [`LICENSE`](../../../LICENSE)
(Apache-2.0). No upstream model, no upstream dataset, no third-party weights are
incorporated.

## Runtime behaviour without them

Optional in the formal sense only. If either file is missing, or if `torch` is
not installed (it is in `requirements-dev.txt`, not `requirements.txt`), the
Director falls back to the model-free planner: the plan source reads
`avoidance (no models)` instead of `search`, and the A/B/C strategy tiles come
back without a forecast. Nothing raises — the degradation is silent, which is
why it is stated in [`README.md`](../../../README.md) and
[`START-HERE.md`](../../../START-HERE.md).

Both paths are overridable: `GOAL_DIRECTED_EVALUATOR` and
`GOAL_DIRECTED_CONNECTION_MODEL`.
