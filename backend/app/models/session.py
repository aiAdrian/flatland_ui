from typing import Any, List, Optional
from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    width: int = Field(default=50, ge=25, le=200, description="grid width")
    height: int = Field(default=20, ge=20, le=150, description="grid height")
    number_of_agents: int = Field(default=3, ge=1, le=50)
    seed: int = 42
    max_num_cities: int = Field(default=4, ge=2, le=10)
    max_rails_between_cities: int = 2
    max_rail_pairs_in_city: int = Field(default=2, ge=1, le=10)
    max_episode_steps: int | None = None
    latest_departure_max: int | None = Field(default=20, ge=0, le=10000)
    speed_profile: str = Field(default="uniform_1_0", description="uniform_1_0 | uniform_0_5 | uniform_0_33 | uniform_0_25 | mixed")
    line_length: int = Field(default=4, ge=1, le=50)

    # Flatland malfunction settings. rate=0 disables malfunctions.
    malfunction_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    malfunction_min_duration: int = Field(default=5, ge=1, le=10000)
    malfunction_max_duration: int = Field(default=20, ge=1, le=10000)

    enabled_policy_ids: list[str] | None = None
    enabled_scenario_policy_ids: list[str] | None = None
    infrastructure_scene: dict[str, Any] | None = None


class SessionInfo(BaseModel):
    id: str
    width: int
    height: int
    num_agents: int


class StepRequest(BaseModel):
    policy: str = Field(default="deadlock_avoidance", description="random | shortest_path | do_nothing | forward_only | deadlock_avoidance")
    n_steps: int = Field(default=1, ge=1, le=100)


class StepResult(BaseModel):
    session_id: str
    elapsed_steps: int
    rewards: dict
    dones: dict
    all_done: bool
