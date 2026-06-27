"""HMI-Mock-Models fuer Notifications, Scenarios, Recommendations."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel


NotificationKind = Literal["info", "warning", "error"]
ElementKind = Literal["train", "switch", "signal"]


class RelatedElement(BaseModel):
    kind: ElementKind
    id: str


class AppNotification(BaseModel):
    id: str
    kind: NotificationKind
    title: str
    message: str
    timestamp: int               # elapsed_steps when raised
    relatedElement: Optional[RelatedElement] = None


class KpiDelta(BaseModel):
    time: Optional[float] = None     # seconds (negative = saved time)
    energy: Optional[float] = None   # kWh delta


class ScenarioKpis(BaseModel):
    totalDelay: int = 0
    deadlocks: int = 0
    done: int = 0
    meanDelay: float = 0.0
    episodeSteps: int = 0
    episodeFinished: bool = False
    episodeSteps: int = 0
    episodeFinished: bool = False
    episodeSteps: int = 0
    episodeFinished: bool = False


class TrajectoryPoint(BaseModel):
    """One agent's position at one simulated step."""
    step: int
    row: int
    col: int
    dir: int  # 0=N, 1=E, 2=S, 3=W

    # Optional Marey/topology debug metadata.
    # Kept optional for backwards-compatible API responses.
    handle: Optional[int] = None
    agent_id: Optional[int] = None
    marey_topology: Optional[str] = None
    marey_svg: Optional[str] = None
    marey_debug: Optional[dict[str, Any]] = None
    marey_switch: Optional[dict[str, Any]] = None
    marey_merge: Optional[dict[str, Any]] = None


class ScenarioOption(BaseModel):
    id: str
    title: str
    description: str
    kpiDelta: KpiDelta
    isRecommended: bool = False
    # Real-scenario fields (None for mock fallback).
    kpis: Optional[ScenarioKpis] = None
    kpiDeltas: Optional[ScenarioKpis] = None
    isBaseline: bool = False
    score: Optional[float] = None
    tag: Optional[str] = None
    # Marey-chart data: per-agent positions over the simulated horizon.
    # Keys are agent handles (as strings, JSON-friendly); values are the
    # on-map points (off-map / WAITING / DONE steps are omitted).
    trajectories: Dict[str, List[TrajectoryPoint]] = {}


class Recommendation(BaseModel):
    id: str
    title: str
    description: str
    confidence: float          # 0..1
    countdownSeconds: int
    scenarioId: Optional[str] = None


class HmiBundle(BaseModel):
    """Alle HMI-Mock-Daten fuer eine Session/Step in einem Rutsch."""
    notifications: List[AppNotification]
    scenarios: List[ScenarioOption]
    recommendations: List[Recommendation]
