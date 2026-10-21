# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""Shared gfx120 (RDNA4) SoC behavior.

Perfmon widths are the same for the gfx120 family. Instance counts such as
L2 banks differ by model and are passed in by soc_gfx1200 / soc_gfx1201.
"""

import argparse
from typing import Optional

from rocprof_compute_soc.soc_base import OmniSoC_Base
from utils.logger import demarcate
from utils.specs import MachineSpecs

# Non-SPM block counter counts from aqlprofile gfx12_block_info.h.
GFX120_PERFMON = {
    "SQ": 16,
    "TA": 2,
    "GRBM": 2,
    "TCP": 4,
    "SPI": 6,
    "GL1A": 4,
    "GL1C": 4,
    "GL2A": 4,
    "GL2C": 4,
    "GCEA": 2,
}


class Gfx120SoC(OmniSoC_Base):
    def __init__(
        self,
        args: argparse.Namespace,
        mspec: MachineSpecs,
        *,
        arch: str,
        l2_banks: int,
        pipes_per_gpu: int,
    ) -> None:
        super().__init__(args, mspec)
        self.set_arch(arch)
        self.set_compatible_profilers(["rocprofv3", "rocprofiler-sdk"])
        self.set_perfmon_config(GFX120_PERFMON)
        self._mspec.l2_banks = l2_banks
        self._mspec.lds_banks_per_cu = 32
        self._mspec.pipes_per_gpu = pipes_per_gpu

    @demarcate
    def profiling_setup(self) -> Optional[list[str]]:
        """Perform any SoC-specific setup prior to profiling."""
        super().profiling_setup()
        return self.perfmon_filter()

    @demarcate
    def post_profiling(self) -> None:
        """Perform any SoC-specific post profiling activities."""
        super().post_profiling()
