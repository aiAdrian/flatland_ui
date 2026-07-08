"""Env factory with robust generation and configurable session properties."""
import warnings
from typing import Optional

from flatland.envs.rail_env import RailEnv
from flatland.envs import rail_generators as rail_gen
from flatland.envs import line_generators as line_gen
import flatland.envs.timetable_generators as ttg
from app.core.infrastructure_scene_adapter import scene_to_line_generator, scene_to_rail_generator


class EnvGenerationError(Exception):
    """Raised when Flatland cannot produce a valid env for the given params."""
    def __init__(self, message: str, params: dict, attempts: int):
        super().__init__(message)
        self.params = params
        self.attempts = attempts


def _speed_ratio_map(profile: str) -> dict[float, float]:
    """Flatland speed profile probabilities."""
    profiles = {
        "uniform_1_0": {1.0: 1.0},
        "uniform_0_5": {0.5: 1.0},
        "uniform_0_33": {0.33: 1.0},
        "uniform_0_25": {0.25: 1.0},
        "mixed": {1.0: 0.25, 0.5: 0.25, 0.33: 0.25, 0.25: 0.25},
    }
    return profiles.get(profile, profiles["uniform_1_0"])


def _apply_latest_departure_limit(env: RailEnv, latest_departure_max: int | None) -> None:
    """Clamp agent earliest departures so no train starts later than the limit."""
    if latest_departure_max is None:
        return
    limit = max(0, int(latest_departure_max))
    for agent in getattr(env, "agents", []):
        if hasattr(agent, "earliest_departure"):
            try:
                current = int(getattr(agent, "earliest_departure") or 0)
                setattr(agent, "earliest_departure", min(current, limit))
            except Exception:
                pass


def _rail_env_supports_malfunction_generator() -> bool:
    """Check whether this Flatland RailEnv accepts malfunction_generator."""
    try:
        import inspect
        sig = inspect.signature(RailEnv)
        if "malfunction_generator" in sig.parameters:
            return True
        return any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
    except Exception:
        # Older / wrapped constructors can be hard to introspect. Try anyway.
        return True


def _build_malfunction_generator(
    malfunction_rate: float | None,
    min_duration: int | None,
    max_duration: int | None,
):
    """Build Flatland malfunction generator if supported and enabled.

    rate <= 0 disables malfunctions.

    Flatland versions differ here:
    - Newer versions prefer ParamMalfunctionGen.
    - malfunction_from_params is deprecated in the installed version and
      can return a tuple, which RailEnv cannot use directly because it
      expects an object with get_process_data().
    """
    try:
        rate = float(malfunction_rate or 0.0)
    except Exception:
        rate = 0.0

    if rate <= 0:
        return None

    min_d = max(1, int(min_duration or 1))
    max_d = max(min_d, int(max_duration or min_d))

    try:
        from flatland.envs.malfunction_generators import MalfunctionParameters
    except Exception as e:
        warnings.warn(f"Flatland MalfunctionParameters unavailable: {e!r}")
        return None

    try:
        params = MalfunctionParameters(
            malfunction_rate=rate,
            min_duration=min_d,
            max_duration=max_d,
        )
    except TypeError:
        # Compatibility with older positional constructor variants.
        params = MalfunctionParameters(rate, min_d, max_d)

    def normalize_generator(gen):
        if gen is None:
            return None
        if hasattr(gen, "get_process_data"):
            return gen
        if isinstance(gen, tuple):
            for item in gen:
                if hasattr(item, "get_process_data"):
                    return item
            warnings.warn(
                "Flatland malfunction generator returned a tuple without "
                "a get_process_data() generator; disabling malfunctions."
            )
            return None
        warnings.warn(
            f"Flatland malfunction generator has unsupported type "
            f"{type(gen)!r}; disabling malfunctions."
        )
        return None

    # Preferred API in current Flatland.
    try:
        from flatland.envs.malfunction_generators import ParamMalfunctionGen
        try:
            return normalize_generator(ParamMalfunctionGen(params))
        except TypeError:
            return normalize_generator(
                ParamMalfunctionGen(
                    malfunction_rate=rate,
                    min_duration=min_d,
                    max_duration=max_d,
                )
            )
    except Exception:
        pass

    # Deprecated fallback for older versions.
    try:
        from flatland.envs.malfunction_generators import malfunction_from_params
        return normalize_generator(malfunction_from_params(params))
    except Exception as e:
        warnings.warn(f"Flatland malfunction generator unavailable: {e!r}")
        return None



def _build_once(
    width,
    height,
    number_of_agents,
    seed,
    max_num_cities,
    max_rails_between_cities,
    max_rail_pairs_in_city,
    speed_profile,
    line_length,
    latest_departure_max,
    malfunction_rate,
    malfunction_min_duration,
    malfunction_max_duration,
    infrastructure_scene=None,
):
    malfunction_generator = _build_malfunction_generator(
        malfunction_rate,
        malfunction_min_duration,
        malfunction_max_duration,
    )

    env_kwargs = {}
    if malfunction_generator is not None and _rail_env_supports_malfunction_generator():
        env_kwargs["malfunction_generator"] = malfunction_generator

    if infrastructure_scene is not None:
        rail_generator = scene_to_rail_generator(infrastructure_scene)
        line_generator = scene_to_line_generator(infrastructure_scene)
    else:
        rail_generator = rail_gen.sparse_rail_generator(
            max_num_cities=max_num_cities,
            seed=seed,
            grid_mode=False,
            max_rails_between_cities=max_rails_between_cities,
            max_rail_pairs_in_city=max_rail_pairs_in_city,
        )
        line_generator = line_gen.sparse_line_generator(
            speed_ratio_map=_speed_ratio_map(speed_profile),
            seed=seed,
            line_length=line_length,
        )

    def make_env(extra_kwargs):
        return RailEnv(
            width=width,
            height=height,
            number_of_agents=number_of_agents,
            rail_generator=rail_generator,
            line_generator=line_generator,
            timetable_generator=ttg.timetable_generator,
            **extra_kwargs,
        )

    try:
        env = make_env(env_kwargs)
    except TypeError as e:
        # Some Flatland versions do not accept malfunction_generator in
        # RailEnv.__init__. Do not fail session creation; disable the
        # generator and continue. The UI still works, just without random
        # malfunctions for that Flatland version.
        if env_kwargs and "malfunction" in str(e).lower():
            warnings.warn(
                f"Flatland RailEnv does not accept malfunction_generator; "
                f"continuing without malfunctions. Original error: {e!r}"
            )
            env = make_env({})
        else:
            raise
    obs, info = env.reset()
    _apply_latest_departure_limit(env, latest_departure_max)
    return env, obs, info


def create_env(
    width: int = 30,
    height: int = 30,
    number_of_agents: int = 3,
    seed: int = 42,
    max_num_cities: int = 2,
    max_rails_between_cities: int = 2,
    max_rail_pairs_in_city: int = 2,
    max_episode_steps: int | None = None,
    latest_departure_max: int | None = 20,
    speed_profile: str = "uniform_1_0",
    line_length: int = 4,
    malfunction_rate: float = 0.0,
    malfunction_min_duration: int = 5,
    malfunction_max_duration: int = 20,
    infrastructure_scene=None,
    max_retries: int = 5,
) -> RailEnv:
    """Build a RailEnv. If Flatland fails, retry with seed+1, seed+2, ..."""
    last_err: Optional[Exception] = None
    params = dict(
        width=width,
        height=height,
        number_of_agents=number_of_agents,
        seed=seed,
        max_num_cities=max_num_cities,
        max_rails_between_cities=max_rails_between_cities,
        max_rail_pairs_in_city=max_rail_pairs_in_city,
        max_episode_steps=max_episode_steps,
        latest_departure_max=latest_departure_max,
        speed_profile=speed_profile,
        line_length=line_length,
        malfunction_rate=malfunction_rate,
        malfunction_min_duration=malfunction_min_duration,
        malfunction_max_duration=malfunction_max_duration,
        infrastructure_scene=infrastructure_scene,
    )

    for attempt in range(max_retries):
        try_seed = seed + attempt
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                env, obs, info = _build_once(
                    width,
                    height,
                    number_of_agents,
                    try_seed,
                    max_num_cities,
                    max_rails_between_cities,
                    max_rail_pairs_in_city,
                    speed_profile,
                    line_length,
                    latest_departure_max,
                    malfunction_rate,
                    malfunction_min_duration,
                    malfunction_max_duration,
                    infrastructure_scene,
                )
                if max_episode_steps is not None and max_episode_steps > 0:
                    env._max_episode_steps = int(max_episode_steps)
                env._initial_obs = obs
                env._initial_info = info
                return env
        except (IndexError, ValueError, RuntimeError) as e:
            last_err = e
            continue

    raise EnvGenerationError(
        f"Flatland could not generate a valid env after {max_retries} retries "
        f"(width={width}, height={height}, agents={number_of_agents}, "
        f"cities={max_num_cities}). Last error: {last_err!r}",
        params=params,
        attempts=max_retries,
    )
