# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

import argparse

from rocprof_compute_soc.gfx120_common import Gfx120SoC
from utils.specs import MachineSpecs


class gfx1201_soc(Gfx120SoC):
    """Radeon AI PRO R9700. The arch path stays gfx1201."""

    def __init__(self, args: argparse.Namespace, mspec: MachineSpecs) -> None:
        # gfx1201::Gl2cCounterBlockNumInstances; rocminfo reports 4 shader engines.
        super().__init__(
            args,
            mspec,
            arch="gfx1201",
            l2_banks=32,
            pipes_per_gpu=4,
        )
