# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""gfx1201 definitions in sdk_config.yaml follow the SDK report."""

from pathlib import Path

import common
import yaml

from utils.utils_common import metrics_config_for_arch

PANEL = [
    "SQ_INSTS_ALL",
    "SQC_DCACHE_HITS",
    "SQC_DCACHE_MISSES",
    "SQC_DCACHE_REQ",
    "TCP_REQ_READ",
    "TCP_REQ_WRITE",
    "GL1C_BUSY",
    "GL1C_CYCLE",
    "GL2C_BUSY",
    "GL2C_CYCLE",
    "GL2C_EA_RDREQ_32B",
    "GL2C_EA_RDREQ_64B",
    "GL2C_EA_RDREQ_128B",
    "SQ_WAVES",
    "GRBM_GUI_ACTIVE",
]
DEAD = ["GL1C_REQ", "GL2C_READ_64_REQ", "GCEA_ALWAYS_COUNT", "GCEA_SARB_BUSY"]
GFX1250_EVENTS = {
    "GL2C_EA_RDREQ_32B": 119,
    "GL2C_EA_RDREQ_64B": 120,
    "GL2C_EA_RDREQ_128B": 121,
    "SQ_INSTS_ALL": 64,
    "GL2C_HIT": 84,
    "GL2C_MISS": 85,
}

_REPO = Path(common.ROOT).resolve().parents[1]
_COMPUTE_CONFIG = (
    Path(common.ROOT)
    / "src"
    / "rocprof_compute_soc"
    / "profile_configs"
    / "sdk_config.yaml"
)
_SDK_REPORT = (
    _REPO
    / "projects"
    / "rocprofiler-sdk"
    / "source"
    / "share"
    / "rocprofiler-sdk"
    / "config.yaml"
)


def _load(path):
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _counters(document):
    return {
        counter["name"]: counter for counter in document["rocprofiler-sdk"]["counters"]
    }


def definition_for(counter, arch):
    """Return the definition whose architectures contain arch, or None."""
    if counter is None:
        return None
    for definition in counter.get("definitions") or []:
        if arch in (definition.get("architectures") or []):
            return definition
    return None


def _signal(definition):
    return (
        definition.get("block"),
        definition.get("event"),
        definition.get("expression"),
    )


_COMPUTE = _counters(_load(_COMPUTE_CONFIG))
_SDK = _counters(_load(_SDK_REPORT))
sdk_config = _load(_COMPUTE_CONFIG)


def test_every_gfx1201_definition_matches_sdk_report():
    # For every compute counter that has a gfx1201 definition, the SDK
    # report has a gfx1201 definition with the same block, event, and
    # expression. gfx12 and gfx1200 on that same compute definition match
    # gfx1201.
    for name, counter in _COMPUTE.items():
        got = definition_for(counter, "gfx1201")
        if got is None:
            continue
        sdk_counter = _SDK.get(name)
        assert sdk_counter is not None, name
        sdk_def = definition_for(sdk_counter, "gfx1201")
        if sdk_def is None:
            # Derived reductions may extend a report expression onto gfx1201
            # when the report lists that expression for other architectures.
            assert got.get("block") is None, name
            assert got.get("event") is None, name
            sdk_expressions = {
                definition.get("expression")
                for definition in sdk_counter.get("definitions") or []
            }
            assert got.get("expression") in sdk_expressions, name
        else:
            assert _signal(got) == _signal(sdk_def), name
        assert "gfx12" in got.get("architectures", []), name
        assert "gfx1200" in got.get("architectures", []), name
        for arch in ("gfx12", "gfx1200"):
            other = definition_for(counter, arch)
            assert other is not None, (name, arch)
            assert _signal(other) == _signal(got), (name, arch)
    for name in PANEL:
        sdk_def = definition_for(_SDK[name], "gfx1201")
        assert sdk_def is not None, name
        for arch in ("gfx12", "gfx1200", "gfx1201"):
            got = definition_for(_COMPUTE[name], arch)
            assert got is not None, (name, arch)
            assert got.get("block") == sdk_def.get("block"), (name, arch)
            assert got.get("event") == sdk_def.get("event"), (name, arch)


def test_panel_sums_reduce_over_gfx1201():
    # Each PANEL name + "_sum" has a gfx1201 definition whose expression
    # is exactly "reduce(<NAME>,sum)".
    for name in PANEL:
        sum_name = name + "_sum"
        definition = definition_for(_COMPUTE.get(sum_name), "gfx1201")
        assert definition is not None, sum_name
        assert definition.get("expression") == f"reduce({name},sum)"


def test_sqg_accum_stays_on_gfx1250_only():
    # architectures == ["gfx1250"]
    # expression == "accumulate(SQG_LEVEL_WGP_ACTIVE, HIGH_RES)"
    # no gfx1201 definition
    counter = _COMPUTE.get("SQG_LEVEL_WGP_ACTIVE_ACCUM")
    assert counter is not None
    definition = definition_for(counter, "gfx1250")
    assert definition is not None
    assert definition.get("architectures") == ["gfx1250"]
    assert definition.get("expression") == "accumulate(SQG_LEVEL_WGP_ACTIVE, HIGH_RES)"
    assert definition_for(counter, "gfx1201") is None


def test_gfx1201_valu_uses_sdk_event_50():
    definition = definition_for(_COMPUTE["SQ_INSTS_VALU"], "gfx1201")
    assert definition is not None
    assert definition.get("block") == "SQ"
    assert definition.get("event") == 50
    summed = definition_for(_COMPUTE["SQ_INSTS_VALU_sum"], "gfx1201")
    assert summed is not None
    assert summed.get("expression") == "reduce(SQ_INSTS_VALU,sum)"


def test_gfx1250_events_stay():
    for name, event in GFX1250_EVENTS.items():
        definition = definition_for(_COMPUTE[name], "gfx1250")
        assert definition is not None, name
        assert definition.get("event") == event, name


def test_dead_counters_have_no_gfx1201_definition():
    for name in DEAD:
        assert definition_for(_COMPUTE[name], "gfx1201") is None, name


def test_gfx1201_metrics_drop_sqg_accum_only():
    filtered = metrics_config_for_arch(sdk_config, "gfx1201")
    names = [c["name"] for c in filtered["rocprofiler-sdk"]["counters"]]
    assert "SQG_LEVEL_WGP_ACTIVE_ACCUM" not in names
    assert "SQ_INSTS_ALL" in names
    assert len(names) == len(sdk_config["rocprofiler-sdk"]["counters"]) - 1


def test_gfx1250_metrics_keep_sqg_accum():
    filtered = metrics_config_for_arch(sdk_config, "gfx1250")
    names = [c["name"] for c in filtered["rocprofiler-sdk"]["counters"]]
    assert "SQG_LEVEL_WGP_ACTIVE_ACCUM" in names
