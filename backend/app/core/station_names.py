"""Station and place names of a scene, for the operator to read.

The PF–CH scenes (Gleisschema Pfäffikon SZ–Chur) carry their geography in the
scene file: a station entry per platform track with an SBB code and a name in
ASCII ("Ziegelbruecke"), and in `metadata` the order of all places along the
line, the column each one sits at, and the single-track section. Places modelled
without tracks (Mühlehorn, Murg, …) appear there as codes only.

`STATION_NAMES` gives every code of the line its proper name; `scene_geography`
turns a scene into what the HMI needs — named platform cells, named places by
column, and the single-track section. Generated networks carry none of this and
get empty lists, so the frontend keeps its own "S1…" labels there.
"""
from __future__ import annotations

from typing import Any

# SBB codes of the Pfäffikon SZ–Chur line, west to east.
STATION_NAMES: dict[str, str] = {
    "PF": "Pfäffikon SZ",
    "ALTD": "Altendorf",
    "LA": "Lachen",
    "SIB": "Siebnen-Wangen",
    "SCBU": "Schübelbach-Buttikon",
    "RG": "Reichenburg",
    "BIL": "Bilten",
    "ZB": "Ziegelbrücke",
    "WN": "Weesen",
    "MH": "Mühlehorn",
    "TIEF": "Tiefenwinkel",
    "MG": "Murg",
    "UNT": "Unterterzen",
    "MOLS": "Mols",
    "WAL": "Walenstadt",
    "FMS": "Flums",
    "MELS": "Mels",
    "SA": "Sargans",
    "BRAG": "Bad Ragaz",
    "MF": "Maienfeld",
    "LQ": "Landquart",
    "ZZS": "Zizers",
    "CH": "Chur",
}


def station_name(code: str | None, fallback: str | None = None) -> str | None:
    """The proper name for a code, else the scene's own spelling."""
    if code and code in STATION_NAMES:
        return STATION_NAMES[code]
    return fallback or code


def scene_geography(scene: Any) -> dict:
    """Named platform cells, named places by column, and the single-track section.

    Empty lists when the scene carries no geography (or there is no scene).
    """
    empty = {"stations": [], "locations": [], "single_track": []}
    if not isinstance(scene, dict):
        return empty

    stations = []
    for st in scene.get("stations") or []:
        if not isinstance(st, dict):
            continue
        meta = st.get("metadata") or {}
        try:
            cell = [int(st["y"]), int(st["x"])]
        except (KeyError, TypeError, ValueError):
            continue
        code = meta.get("code")
        name = station_name(code, meta.get("station") or st.get("name"))
        if not name:
            continue
        track = meta.get("track")
        stations.append({
            "code": code,
            "name": name,
            "track": int(track) if isinstance(track, (int, float)) else None,
            "cell": cell,
        })

    meta = scene.get("metadata") or {}
    columns = meta.get("locationColumns") or {}
    locations = []
    for code in meta.get("locationOrder") or []:
        col = columns.get(code)
        if not isinstance(col, (int, float)):
            continue
        locations.append({"code": code, "name": station_name(code, code), "col": int(col)})

    single = meta.get("singleTrackSection") or []
    return {
        "stations": stations,
        "locations": locations,
        "single_track": [str(c) for c in single] if isinstance(single, list) else [],
    }


__all__ = ["STATION_NAMES", "scene_geography", "station_name"]
