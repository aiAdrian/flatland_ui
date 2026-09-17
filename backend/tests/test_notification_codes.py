"""Notifications carry a stable code and parameters (i18n plan, phase 4).

The frontend words notifications in the viewer's language from `code` +
`params`; `title` and `message` stay the English text and the fallback. These
tests pin the contract the frontend's translation keys depend on.
"""
import warnings

warnings.filterwarnings("ignore")

from types import SimpleNamespace  # noqa: E402

from app.core import hmi_mock  # noqa: E402
from app.core.disturbances import DisturbanceScheduler, notification_code_for  # noqa: E402
from app.core.notification_manager import NotificationManager  # noqa: E402
from app.models.hmi import AppNotification  # noqa: E402


def test_code_and_params_are_optional_for_existing_clients():
    n = AppNotification(id="x", kind="info", title="t", message="m", timestamp=0)
    assert n.code is None and n.params is None


def test_manager_round_trips_code_and_params():
    mgr = NotificationManager()
    mgr.add("s", kind="warning", title="Override risk increase", message="…",
            timestamp=5, related_kind="train", related_id="2",
            code="override.riskIncrease", params={"train": 2, "before": 0, "after": 1})
    [n] = mgr.get_active("s", 5)
    assert n.code == "override.riskIncrease"
    assert n.params == {"train": 2, "before": 0, "after": 1}
    assert n.title == "Override risk increase"  # English text kept as fallback


def test_manager_without_code_stays_as_before():
    mgr = NotificationManager()
    mgr.add("s", kind="info", title="t", message="m", timestamp=1)
    [n] = mgr.get_active("s", 1)
    assert n.code is None and n.params is None


def test_scheduler_events_keep_their_source_file_and_index():
    first = {"id": "file-a", "events": [{"step": 20, "type": "warning"}, {"step": 5, "type": "warning"}]}
    second = {"id": "file-b", "events": [{"step": 10, "type": "train_delay", "agent_handle": 0, "delay_steps": 1}]}
    scheduler = DisturbanceScheduler([first, second])
    identities = [(e["_source"], e["_index"], e["step"]) for e in scheduler.events]
    # sorted by step, but each event still knows where it was authored
    assert identities == [("file-a", 1, 5), ("file-b", 0, 10), ("file-a", 0, 20)]


def test_disturbance_code_names_file_and_event():
    code, params = notification_code_for({"type": "train_delay", "_source": "w1-door-fault", "_index": 0})
    assert code == "disturbance.event"
    assert params == {"type": "train_delay", "disturbance": "w1-door-fault", "event": 0}


def test_disturbance_code_without_source_has_no_identity():
    code, params = notification_code_for({"type": "warning"})
    assert code == "disturbance.event" and params == {"type": "warning"}


def _session_with(agent):
    env = SimpleNamespace(dones={}, agents=[agent])
    return SimpleNamespace(env=env)


def test_generated_malfunction_carries_train_and_steps(monkeypatch):
    agent = SimpleNamespace(handle=3, malfunction_handler=SimpleNamespace(malfunction_down_counter=7))
    from app.core import session_manager as sm_module
    monkeypatch.setattr(sm_module.session_manager, "get", lambda sid: _session_with(agent))
    notes = hmi_mock.generate_notifications("fake-session", 12)
    [mf] = [n for n in notes if n.code == "train.malfunction"]
    assert mf.params == {"train": 3, "steps": 7}
    assert mf.message == "Train 3 is malfunctioning (7 steps remaining)."
