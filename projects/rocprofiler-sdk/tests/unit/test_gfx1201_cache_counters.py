"""gfx1201 cache and fabric counters use soc24 event ids."""

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


def test_gfx1201_gl1c_counters_use_soc24_event_ids():
    events = {
        "GL1C_CYCLE": 0,
        "GL1C_BUSY": 1,
        "GL1C_REQ": 6,
        "GL1C_GL2_REQ_READ_128B": 12,
        "GL1C_GL2_REQ_READ_32B": 13,
        "GL1C_GL2_REQ_READ_64B": 14,
        "GL1C_GL2_REQ_WRITE_32B": 16,
        "GL1C_GL2_REQ_WRITE_64B": 17,
        "GL1C_STALL_GL2_GL1": 18,
    }
    for name, event in events.items():
        assert_gfx12_raw(name, "GL1C", event)


def test_gfx1201_does_not_invent_gl1c_req_miss():
    assert gfx1201_raw("GL1C_REQ_MISS") is None


def test_gfx1201_gl2c_counters_use_soc24_event_ids():
    events = {
        "GL2C_CYCLE": 1,
        "GL2C_BUSY": 2,
        "GL2C_READ_32_REQ": 69,
        "GL2C_READ_64_REQ": 70,
        "GL2C_READ_128_REQ": 71,
        "GL2C_COMPRESSED_READ_96_REQ": 77,
        "GL2C_MC_WRREQ": 79,
        "GL2C_EA_RDREQ_96B": 96,
    }
    for name, event in events.items():
        assert_gfx12_raw(name, "GL2C", event)
    assert gfx1201_raw("GL2C_HIT") == ("GL2C", 41)


def test_gfx1201_tcp_counters_use_soc24_event_ids():
    events = {
        "TCP_REQ_READ": 10,
        "TCP_REQ_WRITE": 14,
        "TCP_GL1_REQ_READ": 30,
        "TCP_GL1_REQ_WRITE": 33,
    }
    for name, event in events.items():
        assert_gfx12_raw(name, "TCP", event)
    assert gfx1201_raw("TCP_REQ") == ("TCP", 9)


def test_gfx1201_gcea_counters_use_soc24_event_ids():
    events = {
        "GCEA_ALWAYS_COUNT": 0,
        "GCEA_SARB_BUSY": 62,
        "GCEA_SARB_STALLED": 63,
        "GCEA_RDRAM_SIZE_REQ": 77,
        "GCEA_WDRAM_SIZE_REQ": 78,
    }
    for name, event in events.items():
        assert_gfx12_raw(name, "GCEA", event)
