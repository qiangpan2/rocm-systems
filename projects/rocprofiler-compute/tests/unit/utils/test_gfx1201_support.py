# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""gfx1201 must be profileable and analyzable for kernel counters."""

import re
from pathlib import Path

import common
from utils.mi_gpu_spec import MIGPUSpecs

# Counters whose create_profile_config succeeded on gfx1201.
COLLECTABLE = {
    "SQ_INSTS_ALL",
    "SQ_INSTS_INTERNAL",
    "SQ_INSTS_VALU_DP",
    "SQC_TC_INST_REQ",
    "SQC_TC_DATA_READ_REQ",
    "SQC_DCACHE_REQ",
    "SQC_DCACHE_HITS",
    "SQC_DCACHE_MISSES",
    "TCP_REQ",
    "TCP_REQ_READ",
    "TCP_REQ_WRITE",
    "TCP_GL1_REQ_READ",
    "TCP_GL1_REQ_WRITE",
    "GL1C_CYCLE",
    "GL1C_BUSY",
    "GL1C_REQ",
    "GL1C_GL2_REQ_READ_128B",
    "GL1C_GL2_REQ_READ_32B",
    "GL1C_GL2_REQ_READ_64B",
    "GL1C_GL2_REQ_WRITE_32B",
    "GL1C_GL2_REQ_WRITE_64B",
    "GL1C_STALL_GL2_GL1",
    "GL2C_CYCLE",
    "GL2C_BUSY",
    "GL2C_READ_32_REQ",
    "GL2C_READ_64_REQ",
    "GL2C_READ_128_REQ",
    "GL2C_COMPRESSED_READ_96_REQ",
    "GL2C_EA_RDREQ_32B",
    "GL2C_EA_RDREQ_64B",
    "GL2C_EA_RDREQ_96B",
    "GL2C_EA_RDREQ_128B",
    "SQ_INSTS_VALU",
    "GCEA_ALWAYS_COUNT",
    "GCEA_SARB_BUSY",
    "GCEA_SARB_STALLED",
    "GCEA_RDRAM_SIZE_REQ",
    "GCEA_WDRAM_SIZE_REQ",
}

# Present in older reports but rejected or missing on this gfx1201.
REJECTED = {
    "GRBM_GUI_ACTIVE",
    "GL2C_HIT",
    "GL2C_MISS",
    "GL2C_MC_WRREQ",
    "GL1C_REQ_MISS",
}

_COUNTER = re.compile(r"\b([A-Z][A-Z0-9_]*(?:_sum|_avr|_min|_max)?)\b")
_FUNCS = {"SUM", "MIN", "MAX", "AVG", "TO_INT", "MAX"}


def _panel_counters() -> set[str]:
    panel_dir = (
        Path(common.SRC)
        / "rocprof_compute_soc"
        / "analysis_configs"
        / "gfx1201"
    )
    found: set[str] = set()
    for path in panel_dir.glob("*.yaml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "value:" not in line:
                continue
            for token in _COUNTER.findall(line):
                if token in _FUNCS:
                    continue
                for suffix in ("_sum", "_avr", "_min", "_max"):
                    if token.endswith(suffix):
                        token = token[: -len(suffix)]
                        break
                found.add(token)
    return found


def test_gfx1201_is_supported_for_profiling():
    assert MIGPUSpecs.get_gpu_series("gfx1201") == "RDNA4"
    assert MIGPUSpecs.get_gpu_model("gfx1201", "30033") == "RDNA4_R9700"
    assert not MIGPUSpecs.is_partition_supported("gfx1201", None)
    from rocprof_compute_soc.gfx120_common import GFX120_PERFMON

    config = MIGPUSpecs.get_perfmon_config("gfx1201")
    assert config == GFX120_PERFMON
    assert "gfx1201" in common.SUPPORTED_ARCHS
    assert "gfx120" not in common.SUPPORTED_ARCHS


def test_gfx1201_path_stays_gfx1201():
    from utils.utils_common import canonical_config_arch

    assert canonical_config_arch("gfx1201") == "gfx1201"


def test_gfx1201_soc_records_hardware_shape():
    import argparse

    from rocprof_compute_soc.gfx120_common import Gfx120SoC
    from rocprof_compute_soc.soc_gfx1201 import gfx1201_soc
    from utils.specs import MachineSpecs

    soc = gfx1201_soc(argparse.Namespace(), MachineSpecs())
    assert isinstance(soc, Gfx120SoC)
    assert soc.get_arch() == "gfx1201"
    assert soc._mspec.l2_banks == 32
    assert soc._mspec.lds_banks_per_cu == 32
    assert soc._mspec.pipes_per_gpu == 4


def test_gfx1201_kernel_panel_uses_only_collectable_counters():
    used = _panel_counters()
    assert used, "gfx1201 analysis panel did not reference any counters"
    assert used <= COLLECTABLE
    assert used.isdisjoint(REJECTED)
    assert used.isdisjoint(
        {"GL1C_REQ", "GCEA_SARB_BUSY", "GCEA_ALWAYS_COUNT", "GL2C_READ_64_REQ"}
    )
    assert "SQ_INSTS_ALL" in used
    assert "GL1C_BUSY" in used
    assert "GL1C_CYCLE" in used
    assert "GL2C_EA_RDREQ_128B" in used
    assert "GL2C_BUSY" in used
    assert "TCP_REQ_READ" in used
