# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""gfx1201 roofline package mapping and the off-chip read panel.

These tests import no HIP library, so they run on a machine without a GPU.
"""

import ast
import inspect
from pathlib import Path

# The brief names this path from the monorepo root. pytest for this project
# runs inside rocprofiler-compute, where the same file is src-relative.
_PANEL_FROM_REPO = Path(
    "projects/rocprofiler-compute/src/rocprof_compute_soc/analysis_configs/gfx1201/0400_roofline.yaml"
)
_PANEL_FROM_PROJECT = Path(
    "src/rocprof_compute_soc/analysis_configs/gfx1201/0400_roofline.yaml"
)

# 96B is a GL2C event on gfx1201, but on the R9700 burn capture it counted
# about once per L2 busy cycle (61,012,416 vs GL2C_BUSY 61,355,581). Weighting
# it by 96 produced 4600 GB/s against a ~576 GB/s GDDR6 roof. 32/64/128 stay.
_OFFCHIP_READ_BYTES = (
    "(32 * SUM(GL2C_EA_RDREQ_32B_sum) + 64 * SUM(GL2C_EA_RDREQ_64B_sum)"
    " + 128 * SUM(GL2C_EA_RDREQ_128B_sum))"
)
_OFFCHIP_READ_BANDWIDTH = (
    f"{_OFFCHIP_READ_BYTES} / SUM(End_Timestamp - Start_Timestamp)"
)
_VALU_LANE_INSTS = "SUM($wave_size * SQ_INSTS_VALU_sum)"
_L0_BYTES = "64 * SUM(TCP_REQ_READ_sum + TCP_REQ_WRITE_sum)"


def _panel_text() -> str:
    for candidate in (
        _PANEL_FROM_REPO,
        _PANEL_FROM_PROJECT,
        Path(__file__).resolve().parents[3] / _PANEL_FROM_PROJECT,
    ):
        if candidate.is_file():
            return candidate.read_text()
    return _PANEL_FROM_PROJECT.read_text()


def test_gfx1201_uses_gfx12_package():
    from roofline.run_benchmark import BENCHMARKING_SUPPORTED, roofline_package

    assert roofline_package("gfx1201") == "gfx12"
    assert roofline_package("gfx1200") == "gfx12"
    assert roofline_package("gfx1250") == "gfx12"
    assert roofline_package("gfx1151") == "gfx11"
    assert roofline_package("gfx942") == "gfx9"
    assert "gfx1201" in BENCHMARKING_SUPPORTED


def test_load_bench_uses_roofline_package_after_remap():
    from roofline.run_benchmark import load_bench

    source = inspect.getsource(load_bench)
    assert 'gfx_device = "gfx942"' in source
    assert "roofline_package(gfx_device)" in source
    assert source.index('gfx_device = "gfx942"') < source.index(
        "roofline_package(gfx_device)"
    )
    assert "gfx_device[:-2]" not in source


def test_gfx1201_datatypes_match_gfx1250():
    from utils.roofline_calc import SUPPORTED_DATATYPES

    assert SUPPORTED_DATATYPES["gfx1201"] == SUPPORTED_DATATYPES["gfx1250"]


def test_gfx1201_roofline_panel_uses_defined_counters():
    text = _panel_text()
    for banned in (
        "SQ_VALU_WMMA",
        "TX_VMW",
        "SP_VALU",
        "GC_EA_SE",
        "GL2C_EA_RDREQ_96B_sum",
        "EA_RD_UNCACHED_32B",
        "GL2C_EA_RDREQ_256B",
        "/ 1e9",
    ):
        assert banned not in text
    assert "GDDR Read Bandwidth" in text
    assert "Off-chip Read Bandwidth" not in text
    assert "HBM" not in text
    assert _OFFCHIP_READ_BANDWIDTH in text
    assert "GB/s" in text
    assert "$GDDRBw_empirical_peak" in text
    assert _VALU_LANE_INSTS in text
    assert f"{_L0_BYTES} / SUM(End_Timestamp - Start_Timestamp)" in text
    assert f"{_VALU_LANE_INSTS} / {_OFFCHIP_READ_BYTES}" in text
    assert f"{_VALU_LANE_INSTS} / ({_L0_BYTES})" in text
    assert "AI GDDR:" in text
    assert "AI L0:" in text
    assert "Performance (GFLOPs):" in text
    assert f"{_VALU_LANE_INSTS} / SUM(End_Timestamp - Start_Timestamp)" in text
    assert "$L0Bw_empirical_peak" in text
    assert "$FP32Flops_empirical_peak" in text
    assert "id: 400" in text
    assert "id: 401" in text
    assert "id: 402" in text


def test_gfx1201_kernel_bytes_omit_the_96b_cycle_counter():
    panel = (
        Path(__file__).resolve().parents[3]
        / "src/rocprof_compute_soc/analysis_configs/gfx1201/0200_kernel_analysis.yaml"
    )
    text = panel.read_text()
    assert "GL2C_EA_RDREQ_96B_sum" not in text
    lines = text.splitlines()
    value = ""
    for index, line in enumerate(lines):
        if "Off-chip Read Bytes:" in line:
            value = lines[index + 1]
            break
    assert "96 *" not in value
    assert _OFFCHIP_READ_BYTES.replace("(", "").replace(")", "") in value.replace(
        "(", ""
    ).replace(")", "")


def test_recorded_burn_read_bandwidth_stays_under_gddr6_peak():
    """8-dispatch burn capture from the R9700 recheck, 2026-10-23.

    max_mclk 1124 MHz on a 256-bit GDDR6 interface is about 576 GB/s when the
    data rate is 16 transfers per memory clock. The old 96B term is the
    4600 GB/s result; the 32/64/128 term is the one the panel now uses.
    """
    requests = {
        32: 524308,
        64: 471364,
        96: 488025988,
        128: 131081,
    }
    time_ns = 10199723
    peak_gbps = (256 / 8) * 1124e6 * 16 / 1e9

    def bandwidth(sizes: tuple[int, ...]) -> float:
        return sum(size * requests[size] for size in sizes) / time_ns

    assert bandwidth((32, 64, 128)) == pytest_approx(6.25, abs=0.05)
    assert bandwidth((32, 64, 128)) < peak_gbps
    assert bandwidth((32, 64, 96, 128)) > 4000


def pytest_approx(value, abs):  # noqa: A002
    from pytest import approx

    return approx(value, abs=abs)


def test_gfx1201_roofline_memory_levels_match_measurable_roofs():
    from utils.mi_gpu_spec import MIGPUSpecs

    assert MIGPUSpecs.get_memory_levels("rdna4_r9700") == ["L0", "GDDR"]


def test_gddr_ceiling_reads_gddr_column_not_hbm():
    from types import SimpleNamespace

    from utils.roofline_calc import calc_ceilings

    points = calc_ceilings(
        {"mem_level": "ALL", "matrix_ops_type": "WMMA"},
        "FP32",
        {"GDDRBw": ["640"], "L0Bw": ["2000"], "FP32Flops": ["4000"]},
        SimpleNamespace(gpu_arch="gfx1201", gpu_model="rdna4_r9700"),
        0,
    )
    assert points["gddr"][2] == 640
    assert points["l0"][2] == 2000
    assert points["hbm"] == []


def _assigned_literal(class_node, attribute):
    for node in class_node.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "__init__":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            target = statement.targets[0]
            if (
                isinstance(target, ast.Attribute)
                and target.attr == attribute
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                return ast.literal_eval(statement.value)
    raise AssertionError(f"{class_node.name} does not assign self.{attribute}")


def _class_def(path, name):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{path} does not define {name}")


def test_bench_gfx1201_matches_gfx1250_ops_without_kernel_source():
    gfx12 = Path(__file__).resolve().parents[3] / "src/roofline/benchmark/gfx12"
    gfx1201 = _class_def(gfx12 / "benchmark_gfx1201.py", "Bench_gfx1201")
    gfx1250 = _class_def(gfx12 / "benchmark_gfx1250.py", "Bench_gfx1250")

    assert len(gfx1201.bases) == 1
    base = gfx1201.bases[0]
    assert isinstance(base, ast.Attribute)
    assert base.attr == "Bench_gfx12"
    assert isinstance(base.value, ast.Name)
    assert base.value.id == "benchmark_gfx12_base"

    assert _assigned_literal(gfx1201, "unsupported_data_types") == [
        "L1",
        "MALL",
        "WMMA-F64",
    ]
    assert _assigned_literal(gfx1201, "matrix_ops") == _assigned_literal(
        gfx1250, "matrix_ops"
    )
    source = (gfx12 / "benchmark_gfx1201.py").read_text()
    assert "__global__" not in source
    assert 'self.tests["GDDR"] = self.tests.pop("HBM")' in source
    assert 'self.csv_cols_map["GDDR"] = "GDDRBw"' in source
    assert 'del self.csv_cols_map["HBM"]' in source
    assert 'self.device_memory_name = "GDDR"' in source
