# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

# -----------------------------------------------------------------------------
# benchmark_gfx1201.py
#
# Benchmarking class for all gfx1201 products
#
# -----------------------------------------------------------------------------

from . import benchmark_gfx12_base


# =============================================================================
# Bench_gfx1201 Class
# =============================================================================
class Bench_gfx1201(benchmark_gfx12_base.Bench_gfx12):
    def __init__(self, device_id: int, cache_sizes: dict) -> None:
        super().__init__(device_id, cache_sizes)

        self.unsupported_data_types = ["L1", "MALL", "WMMA-F64"]
        # R9700 is GDDR, not HBM. The streaming-read kernel is unchanged;
        # only the roof name and roofline.csv column change.
        self.device_memory_name = "GDDR"
        self.tests["GDDR"] = self.tests.pop("HBM")
        self.csv_cols_map["GDDR"] = "GDDRBw"
        del self.csv_cols_map["HBM"]

        self.matrix_ops = {
            "F4": 65536,
            "F6": 65536,
            "F6F4": 65536,  # Mixed precision F6 x F4
            "MXF8": 65536,  # microscaling FP8 format
            "F8": 32768,
            "F16": 16384,
            "F32": 2048,
            "F64": 0,  # Unsupported
            "BF16": 16384,
            "I8": 32768,
        }
