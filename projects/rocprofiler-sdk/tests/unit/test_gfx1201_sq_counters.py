"""gfx1201 SQ and SQC counters added for the R9700 report."""

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


def gfx1201_expr(name):
    return _definition(name, "gfx1201", "expr")


def assert_gfx12_raw(name, block, event):
    for arch in ARCHES:
        assert _definition(name, arch, "raw") == (block, event), arch
    assert gfx1201_expr(f"{name}_sum") == f"reduce({name},sum)"


def test_gfx1201_added_sq_counters():
    events = {
        "SQ_INSTS_ALL": 39,
        "SQC_TC_INST_REQ": 315,
        "SQC_DCACHE_REQ": 325,
        "SQC_DCACHE_HITS": 326,
        "SQC_DCACHE_MISSES": 327,
    }
    for name, event in events.items():
        assert_gfx12_raw(name, "SQ", event)
