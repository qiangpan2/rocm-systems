"""gfx1201 cache counters added for the R9700 report."""

from functools import cache
from pathlib import Path

import yaml

CONFIG = (
    Path(__file__).resolve().parents[2]
    / "source"
    / "share"
    / "rocprofiler-sdk"
    / "config.yaml"
)
ARCHES = ("gfx12", "gfx1200", "gfx1201")


@cache
def _counters():
    data = yaml.safe_load(CONFIG.read_text())
    return {item["name"]: item for item in data["rocprofiler-sdk"]["counters"]}


def _definition(name, arch, kind):
    item = _counters().get(name)
    assert item is not None, f"{name} is not in config.yaml"
    for definition in item.get("definitions") or []:
        if arch not in (definition.get("architectures") or []):
            continue
        if kind == "raw" and "block" in definition:
            return definition["block"], int(definition["event"])
        if kind == "expr" and "expression" in definition:
            return definition["expression"]
    return None


def gfx1201_raw(name):
    return _definition(name, "gfx1201", "raw")


def gfx1201_expr(name):
    return _definition(name, "gfx1201", "expr")


def assert_gfx12_raw(name, block, event):
    for arch in ARCHES:
        assert _definition(name, arch, "raw") == (block, event), arch
    assert gfx1201_expr(f"{name}_sum") == f"reduce({name},sum)"


def test_gfx1201_added_cache_counters():
    events = {
        "GL1C_CYCLE": ("GL1C", 0),
        "GL1C_BUSY": ("GL1C", 1),
        "GL1C_REQ": ("GL1C", 30),
        "GL1C_GL2_REQ_READ_32B": ("GL1C", 36),
        "GL1C_GL2_REQ_READ_64B": ("GL1C", 37),
        "GL1C_GL2_REQ_READ_128B": ("GL1C", 38),
        "GL1C_GL2_REQ_WRITE_32B": ("GL1C", 42),
        "GL2C_CYCLE": ("GL2C", 1),
        "GL2C_BUSY": ("GL2C", 2),
        "GL2C_READ_32_REQ": ("GL2C", 78),
        "GL2C_READ_64_REQ": ("GL2C", 79),
        "GL2C_READ_128_REQ": ("GL2C", 80),
        "TCP_REQ_READ": ("TCP", 10),
        "TCP_REQ_WRITE": ("TCP", 14),
    }
    for name, (block, event) in events.items():
        assert_gfx12_raw(name, block, event)


def test_gfx1201_omits_unnamed_gcea_counters():
    assert gfx1201_raw("GCEA_ALWAYS_COUNT") is None
    assert gfx1201_raw("GCEA_SARB_BUSY") is None
