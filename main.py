"""Forecast a big launch's release-day Twitch curve, hour by hour.

The shape of a launch day is set mostly by *when* each part of the world
unlocks. A game that unlocks at midnight local time starts the UTC day
with only the Pacific and Asia awake, then climbs as Europe and the
Americas come online; a game with one early global unlock starts near
its peak and fades; a game whose global unlock lands mid-day explodes
from almost nothing. Hour 1's print anchors the level. The shape --
each later hour's ratio to hour 1 -- is borrowed from the case's own
comparable launches: each comparable is grouped by the shape its own
release day actually took (flat, rising, or explosive), and the groups
are weighted by how well they match the unlock pattern the case notes
describe for the target, times the tier the house gave the comparable.
The spread comes from how much the weighted pool disagreed, shrunk
toward a random-walk prior so a small pool cannot claim false certainty.

Everything is computed from the case file. No network, no randomness, no
wall clock: the same case always writes the same bytes.
"""

import json
import math
import os
import re
from datetime import datetime
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles at the five levels.
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]
# The house baseline's spread: a log random walk, 0.15 per root-hour.
BASE_SIGMA = 0.15
# Pseudo-count of the spread prior: how strongly the empirical spread is
# shrunk toward the random-walk prior when the pool is small.
PRIOR_N = 10.0
# Global multiplier on the shrunk spread (tuned on leave-one-out).
SPREAD_MULT = 0.7
# A pool smaller than this for an hour falls back to the baseline row.
MIN_CURVES = 3
# Quantile clamps from the contest's output contract.
Q_MIN = 1.0
Q_MAX = 1_000_000_000.0

TIER_WEIGHTS = {
    "comparable": 1.0,
    "early-access-contaminated": 0.25,
    "weak": 0.15,
}
# Shape-group weights by the target's unlock pattern, from the notes:
# a rolling target leans on rising curves, a global one on flat curves,
# and an unclear target pools everything evenly.
CLUSTER_WEIGHTS = {
    "rolling": {"flat": 0.4, "rising": 1.0, "explosive": 0.15},
    "global": {"flat": 1.0, "rising": 0.4, "explosive": 0.3},
    "": {"flat": 1.0, "rising": 1.0, "explosive": 1.0},
}
# Peak-ratio cutoffs (in log units) between the shape groups.
FLAT_CUT = math.log(1.6)
EXPLOSIVE_CUT = math.log(20.0)

_TIER_RE = re.compile(r"Tier:\s*([^.\n]+)", re.IGNORECASE)
_ROLLING_HINTS = (
    "midnight local",
    "rolling",
    "local midnight",
    "midnight in every",
    "midnight in each",
    "midnight, country",
)
_GLOBAL_HINTS = (
    "global unlock",
    "simultaneous",
    "single global",
    "one global",
    "worldwide launch",
    "global launch",
)


def _parse_time(text):
    """ISO-8601 with a Z suffix to an aware UTC datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _tier_weight(unlock_text):
    """Weight for a comparable from the tier the house gave it.

    Returns (weight, excluded). The target's own pre-release history is
    not a launch curve and is excluded from the shape pool.
    """
    match = _TIER_RE.search(unlock_text or "")
    tier = match.group(1).strip().lower() if match else ""
    if tier == "target-history":
        return 0.0, True
    return TIER_WEIGHTS.get(tier, 0.5), False


def _pattern(text):
    """Which unlock pattern a text describes: 'rolling', 'global', or ''."""
    lowered = (text or "").lower()
    rolling = any(hint in lowered for hint in _ROLLING_HINTS)
    glob = any(hint in lowered for hint in _GLOBAL_HINTS)
    if rolling and not glob:
        return "rolling"
    if glob and not rolling:
        return "global"
    return ""


def _offset_map(rows, day_start):
    """{whole-hour offset from day_start: viewers} for hourly rows."""
    out = {}
    for row in rows or []:
        try:
            at = _parse_time(row["from"])
            viewers = float(row.get("viewers", 0) or 0)
        except (KeyError, TypeError, ValueError):
            continue
        offset = (at - day_start).total_seconds() / 3600.0
        if offset == int(offset):
            out[int(offset)] = viewers
    return out


def _shape_group(ratios):
    """Flat, rising, or explosive, by the curve's peak ratio to hour 1."""
    peak = max(ratios.values())
    if peak < FLAT_CUT:
        return "flat"
    if peak > EXPLOSIVE_CUT:
        return "explosive"
    return "rising"


def _extract_curves(case):
    """One log-ratio curve per usable comparable, with its weight."""
    notes = case.get("notes") or ""
    if isinstance(notes, dict):
        notes = " ".join(str(v) for v in notes.values())
    cluster_w = CLUSTER_WEIGHTS[_pattern(notes)]
    curves = []
    for comp in case.get("comparables") or []:
        name = (comp.get("name") or "").lower()
        if "before release" in name:
            continue
        tier_w, excluded = _tier_weight(comp.get("unlock") or "")
        if excluded or tier_w <= 0:
            continue
        try:
            day_start = _parse_time(comp["day_start"])
        except (KeyError, TypeError, ValueError):
            continue
        offsets = _offset_map(comp.get("hourly") or [], day_start)
        points = {off + 1: v for off, v in offsets.items() if 0 <= off < 24}
        if 1 not in points or len(points) < 20:
            continue
        first = max(1.0, float(points[1]))
        ratios = {}
        for hour in range(2, 25):
            if hour in points:
                ratios[hour] = math.log(max(1.0, float(points[hour])) / first)
        if len(ratios) < 20:
            continue
        weight = tier_w * cluster_w[_shape_group(ratios)]
        curves.append({"ratios": ratios, "weight": weight})
    return curves


def _weighted_median(pairs):
    """Median of values with weights; pairs is a list of (value, weight)."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    half = total / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= half:
            return value
    return ordered[-1][0]


def _weighted_mean_var(pairs):
    """Weighted mean and population variance of (value, weight) pairs."""
    total = sum(w for _, w in pairs)
    mean = sum(v * w for v, w in pairs) / total
    var = sum(w * (v - mean) ** 2 for v, w in pairs) / total
    return mean, var


def _baseline_row(p1, hour):
    """The house baseline's row: flat median, widening random-walk spread."""
    spread = BASE_SIGMA * math.sqrt(hour - 1)
    return [min(max(p1 * math.exp(z * spread), Q_MIN), Q_MAX) for z in Z]


def baseline_forecast(p1, hours):
    """The whole baseline forecast, used as the fallback everywhere."""
    p1 = min(max(float(p1), Q_MIN), Q_MAX)
    return {"hours": [{"hour": h, "q": _baseline_row(p1, h)} for h in hours]}


def _hour_row(p1, hour, curves):
    """One hour's five quantiles from the pooled comparable curves."""
    pairs = [(c["ratios"][hour], c["weight"]) for c in curves if hour in c["ratios"]]
    if len(pairs) < MIN_CURVES:
        return _baseline_row(p1, hour)
    median = _weighted_median(pairs)
    _, var = _weighted_mean_var(pairs)
    total_w = sum(w for _, w in pairs)
    prior_var = (BASE_SIGMA * math.sqrt(hour - 1)) ** 2
    sd = math.sqrt((total_w * var + PRIOR_N * prior_var) / (total_w + PRIOR_N))
    sd = min(max(sd * SPREAD_MULT, 0.05), 1.5)
    quantiles = []
    floor = Q_MIN
    for z in Z:
        q = min(max(p1 * math.exp(median + z * sd), Q_MIN), Q_MAX)
        q = max(q, floor)
        floor = q
        quantiles.append(q)
    return quantiles


def forecast_case(case):
    """Forecast hours 2..24 of one case from its own comparables."""
    known = case.get("known") or []
    first = next((k for k in known if k.get("hour") == 1), None)
    if first is None and known:
        first = known[0]
    if first is None:
        raise ValueError("case has no hour-1 print")
    p1 = min(max(float(first.get("viewers", 1) or 1), Q_MIN), Q_MAX)
    curves = _extract_curves(case)
    hours = sorted(row["hour"] for row in case.get("forecast") or [])
    if not hours:
        hours = list(range(2, 25))
    rows = [{"hour": h, "q": _hour_row(p1, h, curves)} for h in hours]
    return {"hours": rows}


def _fallback_p1(path):
    """Best-effort hour-1 print from a case file that failed to forecast."""
    try:
        case = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 1.0
    for row in case.get("known") or []:
        if row.get("hour") == 1:
            try:
                return min(max(float(row.get("viewers", 1) or 1), Q_MIN), Q_MAX)
            except (TypeError, ValueError):
                return 1.0
    return 1.0


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            forecast = forecast_case(case)
        except Exception:
            forecast = baseline_forecast(_fallback_p1(path), list(range(2, 25)))
        out_path = OUTPUT_DIR / f"{path.stem}.out"
        out_path.write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
