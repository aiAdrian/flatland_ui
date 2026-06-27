from types import SimpleNamespace

from flatland.envs.rail_env import RailEnvActions

from app.core.override_manager import override_manager
from app.policies.override_policy import OverridePolicy


class DummyPolicy:
    def reset(self, env):
        self.env = env

    def start_step(self):
        pass

    def end_step(self):
        pass

    def act_many(self, handles, observations):
        # Base policy says FORWARD.
        return {int(h): RailEnvActions.MOVE_FORWARD for h in handles}


def _env_at(pos=(1, 1), direction=1):
    agent = SimpleNamespace(
        position=pos,
        direction=direction,
        state=SimpleNamespace(name="MOVING"),
    )
    return SimpleNamespace(agents=[agent])


def test_override_is_pending_until_decision_point(monkeypatch):
    session_id = "test-pending-dp"
    override_manager.clear_all(session_id)

    env = _env_at(pos=(1, 1), direction=1)
    policy = OverridePolicy(DummyPolicy(), session_id)
    policy.reset(env)

    # User pressed STOP, but train is not yet at DP.
    override_manager.set(session_id, 0, RailEnvActions.STOP_MOVING.value)

    monkeypatch.setattr(
        "app.policies.override_policy.classify_cell_at",
        lambda env, pos, direction: "FORWARD_ONLY",
    )

    actions = policy.act_many([0], {0: object()})

    assert actions[0] == RailEnvActions.MOVE_FORWARD
    assert override_manager.get(session_id, 0) == RailEnvActions.STOP_MOVING.value


def test_non_stop_override_applies_once_at_decision_point_and_clears(monkeypatch):
    session_id = "test-active-dp"
    override_manager.clear_all(session_id)

    env = _env_at(pos=(5, 5), direction=1)
    policy = OverridePolicy(DummyPolicy(), session_id)
    policy.reset(env)

    # FORWARD/LEFT/RIGHT are one-shot decision actions.
    override_manager.set(session_id, 0, RailEnvActions.MOVE_FORWARD.value)

    monkeypatch.setattr(
        "app.policies.override_policy.classify_cell_at",
        lambda env, pos, direction: "SWITCH",
    )

    # At DP: FORWARD override applies once.
    actions = policy.act_many([0], {0: object()})
    assert actions[0] == RailEnvActions.MOVE_FORWARD

    # Non-STOP override is consumed.
    assert override_manager.get(session_id, 0) is None

    # Next call uses base policy again.
    actions = policy.act_many([0], {0: object()})
    assert actions[0] == RailEnvActions.MOVE_FORWARD


def test_stop_override_stays_active_at_decision_point_until_cleared(monkeypatch):
    session_id = "test-stop-sticky-at-dp"
    override_manager.clear_all(session_id)

    env = _env_at(pos=(7, 7), direction=1)
    policy = OverridePolicy(DummyPolicy(), session_id)
    policy.reset(env)

    override_manager.set(session_id, 0, RailEnvActions.STOP_MOVING.value)

    monkeypatch.setattr(
        "app.policies.override_policy.classify_cell_at",
        lambda env, pos, direction: "SWITCH",
    )

    # First DP tick: STOP applies.
    actions = policy.act_many([0], {0: object()})
    assert actions[0] == RailEnvActions.STOP_MOVING
    assert override_manager.get(session_id, 0) == RailEnvActions.STOP_MOVING.value

    # Still same DP: STOP keeps applying.
    actions = policy.act_many([0], {0: object()})
    assert actions[0] == RailEnvActions.STOP_MOVING
    assert override_manager.get(session_id, 0) == RailEnvActions.STOP_MOVING.value

    # User clears override: base policy takes over again.
    override_manager.clear(session_id, 0)
    actions = policy.act_many([0], {0: object()})
    assert actions[0] == RailEnvActions.MOVE_FORWARD
    assert override_manager.get(session_id, 0) is None


def test_stop_override_can_be_replaced_by_forward_at_same_decision_point(monkeypatch):
    session_id = "test-stop-replaced-by-forward"
    override_manager.clear_all(session_id)

    env = _env_at(pos=(8, 8), direction=1)
    policy = OverridePolicy(DummyPolicy(), session_id)
    policy.reset(env)

    monkeypatch.setattr(
        "app.policies.override_policy.classify_cell_at",
        lambda env, pos, direction: "SWITCH",
    )

    # STOP becomes sticky.
    override_manager.set(session_id, 0, RailEnvActions.STOP_MOVING.value)
    actions = policy.act_many([0], {0: object()})
    assert actions[0] == RailEnvActions.STOP_MOVING
    assert override_manager.get(session_id, 0) == RailEnvActions.STOP_MOVING.value

    # User replaces STOP with FORWARD.
    # FORWARD is a one-shot decision action and clears after application.
    override_manager.set(session_id, 0, RailEnvActions.MOVE_FORWARD.value)
    actions = policy.act_many([0], {0: object()})
    assert actions[0] == RailEnvActions.MOVE_FORWARD
    assert override_manager.get(session_id, 0) is None
