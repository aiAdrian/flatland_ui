"""
Resolves Flatland uint16 transition values to SVG tile names + rotation.

Logic ported from flatland.utils.graphics_pil.PILSVG.load_rail()
"""
from typing import Dict, List, Optional, Tuple

from flatland.envs.grid.rail_env_grid import RailEnvTransitions

# Base mapping: transition string (NESW notation) -> SVG file name
# Source: flatland.utils.graphics_pil.PILSVG.load_rail() rail_files
RAIL_FILES: Dict[str, str] = {
    "WE":                       "Gleis_Deadend.svg",
    "WW EE NN SS":              "Gleis_Diamond_Crossing.svg",
    "WW EE":                    "Gleis_horizontal.svg",
    "EN SW":                    "Gleis_Kurve_oben_links.svg",
    "WN SE":                    "Gleis_Kurve_oben_rechts.svg",
    "ES NW":                    "Gleis_Kurve_unten_links.svg",
    "NE WS":                    "Gleis_Kurve_unten_rechts.svg",
    "NN SS":                    "Gleis_vertikal.svg",
    "NN SS EE WW ES NW SE WN":  "Weiche_Double_Slip.svg",
    "EE WW EN SW":              "Weiche_horizontal_oben_links.svg",
    "EE WW SE WN":              "Weiche_horizontal_oben_rechts.svg",
    "EE WW ES NW":              "Weiche_horizontal_unten_links.svg",
    "EE WW NE WS":              "Weiche_horizontal_unten_rechts.svg",
    "NN SS EE WW NW ES":        "Weiche_Single_Slip.svg",
    "NE NW ES WS":              "Weiche_Symetrical.svg",
    "NN SS EN SW":              "Weiche_vertikal_oben_links.svg",
    "NN SS SE WN":              "Weiche_vertikal_oben_rechts.svg",
    "NN SS NW ES":              "Weiche_vertikal_unten_links.svg",
    "NN SS NE WS":              "Weiche_vertikal_unten_rechts.svg",
    "NE NW ES WS SS NN":        "Weiche_Symetrical_gerade.svg",
    "NE EN SW WS":              "Gleis_Kurve_oben_links_unten_rechts.svg",
}

_DIRECTIONS = "NESW"


def _transition_string_to_uint16(transition: str) -> int:
    """Convert NESW string like 'EN SW' to 16-bit transition int."""
    bits = ["0"] * 16
    for token in transition.split(" "):
        if len(token) == 2:
            in_dir = _DIRECTIONS.index(token[0])
            out_dir = _DIRECTIONS.index(token[1])
            idx = 4 * in_dir + out_dir
            bits[idx] = "1"
    return int("".join(bits), 2)


def _build_lookup() -> Dict[int, Tuple[str, int]]:
    """
    Build mapping: uint16_transition -> (svg_filename, rotation_degrees).

    Each base transition is rotated 0/90/180/270 degrees, producing 4 entries
    per base type (some collapse if symmetric). Rotating one 2-way switch's
    artwork by 180 degrees reproduces another switch's own un-rotated
    geometry bit-for-bit, so several transition values have more than one
    valid (svg, rotation) label; first entry wins in RAIL_FILES iteration
    order (flatland.utils.graphics_pil.PILSVG.load_pngs resolves the same
    ambiguity the opposite way - unconditional overwrite, i.e. last entry
    wins - since it only needs *a* correctly-oriented image, not a specific
    canonical name). The Infrastructure Builder canvas never rotates switch
    tiles - it always draws one of the 8 named Weiche_* assets un-rotated,
    keyed by connections + switchFacing - so the canonical (rotation=0)
    label is the one that matches what it renders.
    """
    transitions = RailEnvTransitions()
    lookup: Dict[int, Tuple[str, int]] = {}

    for trans_str, svg_file in RAIL_FILES.items():
        base_uint16 = _transition_string_to_uint16(trans_str)

        # rotation 0
        if base_uint16 not in lookup:
            lookup[base_uint16] = (svg_file, 0)

        # rotations 90, 180, 270
        for rot in (90, 180, 270):
            rotated = transitions.rotate_transition(base_uint16, rot)
            if rotated not in lookup:
                lookup[rotated] = (svg_file, rot)

    # Two ambiguous values land, under the iteration order above, on an
    # earlier sibling switch's rotated artwork instead of their own
    # canonical form. Pin those explicitly rather than depend on
    # RAIL_FILES dict order to pick the canvas-matching label.
    for trans_str in ("EE WW ES NW", "NN SS NW ES"):
        lookup[_transition_string_to_uint16(trans_str)] = (RAIL_FILES[trans_str], 0)

    return lookup


# Pre-compute lookup table once on module import
_LOOKUP: Dict[int, Tuple[str, int]] = _build_lookup()


def resolve_tile(uint16_transition: int) -> Optional[Tuple[str, int]]:
    """
    Returns (svg_filename, rotation_degrees) for a given Flatland transition.

    Returns None if cell is empty (transition == 0) or unknown.
    """
    if uint16_transition == 0:
        return None
    return _LOOKUP.get(int(uint16_transition))


def build_rail_tiles(rail_grid: List[List[int]]) -> List[Dict]:
    """
    Convert a 2D rail grid (uint16) into a list of tile descriptors.

    Each tile = {"r": row, "c": col, "svg": filename, "rot": degrees}
    Empty cells are skipped.
    """
    tiles = []
    for r, row in enumerate(rail_grid):
        for c, value in enumerate(row):
            if value == 0:
                continue
            resolved = resolve_tile(value)
            if resolved is None:
                tiles.append({
                    "r": r, "c": c,
                    "svg": "Gleis_horizontal.svg",  # fallback
                    "rot": 0,
                    "unknown": int(value),
                })
            else:
                svg, rot = resolved
                tiles.append({"r": r, "c": c, "svg": svg, "rot": rot})
    return tiles
