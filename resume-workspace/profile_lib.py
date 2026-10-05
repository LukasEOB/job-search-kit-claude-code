# -*- coding: utf-8 -*-
"""One place for everything personal: profile.json at the repo root.

Scripts and hooks import load_profile() instead of hard-coding a person's name, lane resumes,
search keywords, markets, pay tiers or scoring lists. profile.example.json documents every key.
"""
import json, os

MISSING_MSG = ("profile.json not found. Copy profile.example.json to profile.json at the repo root "
               "and fill it in (README.md, step 2).")


# Optional override: JOB_KIT_PROFILE=<path to a profile file>. pipeline_selftest.py uses it to run
# against profile.example.json when no profile.json exists; tests use it to pin a fixture profile.
PROFILE_ENV = "JOB_KIT_PROFILE"


def find_profile(start=None):
    forced = os.environ.get(PROFILE_ENV)
    if forced:
        return os.path.abspath(forced) if os.path.exists(forced) else None
    d = os.path.abspath(start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    for _ in range(8):
        p = os.path.join(d, "profile.json")
        if os.path.exists(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(here, "profile.json")
    return p if os.path.exists(p) else None


def load_profile(start=None):
    """Return the profile dict. Raises FileNotFoundError(MISSING_MSG) when there is none."""
    p = find_profile(start)
    if not p:
        raise FileNotFoundError(MISSING_MSG)
    with open(p, encoding="utf8") as f:
        return json.load(f)


def get(profile, dotted, default=None):
    """get(profile, "search.coreKeywords", []) -> nested value or default."""
    cur = profile
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def pattern(value, default=""):
    """A profile regex value: a string, or a list of alternatives joined with "|". Empty -> default."""
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return "|".join(str(v) for v in value) if value else default
    return str(value) if value != "" else default


# ---- Resume quality gates (.claude/hooks/verify_render.py, check_output.py) ----

# Defaults for the profile key `gates`. A profile that omits a key gets exactly these values, so
# adding a profile never changes gate behavior by accident.
GATE_DEFAULTS = {
    "summaryWords": {"targetMin": 50, "targetMax": 70, "hardMax": 75},
    "atsFloor": 0.85,
    "deEchoWords": 4,
    "summaryExemptConfigPrefixes": ["SUBMITTED-"],
    "rereadExemptWords": [],
    "coverLetterMaxWords": 220,
    "answerMaxWords": 110,
}


def load_profile_optional(start=None):
    """Return (profile, path), or (None, None) when no profile.json exists, so a gate can run on
    its built-in defaults before the owner has set one up. Raises when JOB_KIT_PROFILE names a
    missing file, and when a profile exists but does not parse: a typo must never silently switch
    a configured rule off."""
    forced = os.environ.get(PROFILE_ENV)
    if forced and not os.path.exists(forced):
        raise FileNotFoundError("%s=%s does not exist" % (PROFILE_ENV, forced))
    p = find_profile(start)
    if not p:
        return None, None
    with open(p, encoding="utf8") as f:
        return json.load(f), p


def gates(profile):
    """GATE_DEFAULTS overlaid with the profile's `gates` key (one level deep for dict values).
    Keys starting with "_" are documentation and ignored."""
    out = json.loads(json.dumps(GATE_DEFAULTS))
    for k, v in ((profile or {}).get("gates") or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update({a: b for a, b in v.items() if not a.startswith("_")})
        else:
            out[k] = v
    return out
