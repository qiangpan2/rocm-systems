# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""Shared gfx120 (RDNA4) SoC behavior.

Perfmon widths are the same for the gfx120 family. Instance counts such as
L2 banks differ by model and are passed in by soc_gfx1200 / soc_gfx1201.
"""

import argparse
from typing import Any, Optional

from rocprof_compute_soc.soc_base import OmniSoC_Base
from utils import amdsmi_interface
from utils.logger import console_error, demarcate
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
        # Stable ASIC identities whose perf level was set to STABLE_STD.
        # amdsmi_ctx shuts down before post_profiling, so handles from setup
        # are not reused. Identity is asic_serial, or (device_id, arch).
        self._switched_perf_ids: list[tuple[Any, ...]] = []

    def _processor_handles(self, amdsmi: Any) -> list[Any]:  # noqa: ANN401
        try:
            return list(amdsmi.amdsmi_get_processor_handles() or [])
        except Exception as exc:
            console_error(
                "profiling",
                f"Failed to enumerate AMD processors: {exc}",
                exit=False,
            )
            return []

    def _gpu_asic_info(
        self,
        amdsmi: Any,  # noqa: ANN401
        handle: Any,  # noqa: ANN401
    ) -> Optional[dict[str, Any]]:
        """Return ASIC info, or None if the read fails."""
        try:
            asic = amdsmi.amdsmi_get_gpu_asic_info(handle)
        except Exception as exc:
            console_error(
                "profiling",
                f"Failed to read GPU ASIC info: {exc}",
                exit=False,
            )
            return None
        if not isinstance(asic, dict):
            console_error(
                "profiling",
                f"GPU ASIC info for {handle} is not a mapping",
                exit=False,
            )
            return None
        return asic

    @staticmethod
    def _perf_identity(asic: dict[str, Any]) -> Optional[tuple[Any, ...]]:
        """Prefer asic_serial. Otherwise (device_id, target_graphics_version)."""
        serial = asic.get("asic_serial")
        if serial is not None:
            text = str(serial).strip()
            if text and text.upper() != "N/A":
                return ("asic_serial", text)
        if "device_id" not in asic or "target_graphics_version" not in asic:
            return None
        return (
            "device",
            asic["device_id"],
            asic["target_graphics_version"],
        )

    def _find_processor(
        self,
        amdsmi: Any,  # noqa: ANN401
        identity: tuple[Any, ...],
    ) -> tuple[Any, Optional[dict[str, Any]]]:
        """Return the handle and ASIC info for identity, if present."""
        for handle in self._processor_handles(amdsmi):
            asic = self._gpu_asic_info(amdsmi, handle)
            if asic is None:
                continue
            if self._perf_identity(asic) == identity:
                return handle, asic
        return None, None

    def _set_perf_level(  # noqa: ANN401
        self,
        amdsmi: Any,  # noqa: ANN401
        handle: Any,  # noqa: ANN401
        level: Any,  # noqa: ANN401
    ) -> bool:
        """Set one processor's perf level. Log and continue on failure."""
        try:
            amdsmi.amdsmi_set_gpu_perf_level(handle, level)
        except Exception as exc:
            console_error(
                "profiling",
                f"Failed to set GPU performance level to {level}: {exc}",
                exit=False,
            )
            return False
        return True

    def _with_amdsmi(self, action: Any) -> None:  # noqa: ANN401
        """Run action(amdsmi) inside amdsmi_ctx. Log and return if unavailable."""
        if amdsmi_interface.import_amdsmi_module() is None:
            console_error(
                "profiling",
                "amdsmi is unavailable; skipping GPU performance level change",
                exit=False,
            )
            return
        with amdsmi_interface.amdsmi_ctx():
            amdsmi = amdsmi_interface.import_amdsmi_module()
            if amdsmi is None:
                console_error(
                    "profiling",
                    "amdsmi is unavailable; skipping GPU performance level change",
                    exit=False,
                )
                return
            action(amdsmi)

    @demarcate
    def profiling_setup(self) -> Optional[list[str]]:
        """Set STABLE_STD on this arch, then return the perfmon filter."""
        super().profiling_setup()
        self._switched_perf_ids = []

        def _set_stable(amdsmi: Any) -> None:  # noqa: ANN401
            level = amdsmi.AmdSmiDevPerfLevel.STABLE_STD
            for handle in self._processor_handles(amdsmi):
                asic = self._gpu_asic_info(amdsmi, handle)
                if asic is None:
                    continue
                version = asic.get("target_graphics_version")
                if version != self.get_arch():
                    continue
                identity = self._perf_identity(asic)
                if identity is None:
                    console_error(
                        "profiling",
                        "GPU has no asic_serial or device_id; not switching "
                        "performance level",
                        exit=False,
                    )
                    continue
                if self._set_perf_level(amdsmi, handle, level):
                    self._switched_perf_ids.append(identity)

        self._with_amdsmi(_set_stable)
        return self.perfmon_filter()

    @demarcate
    def post_profiling(self) -> None:
        """Restore AUTO on processors switched to STABLE_STD."""
        super().post_profiling()
        if not self._switched_perf_ids:
            return

        def _restore_auto(amdsmi: Any) -> None:  # noqa: ANN401
            level = amdsmi.AmdSmiDevPerfLevel.AUTO
            for identity in self._switched_perf_ids:
                handle, asic = self._find_processor(amdsmi, identity)
                if handle is None or asic is None:
                    console_error(
                        "profiling",
                        f"Switched GPU {identity} was not found; "
                        "cannot restore AUTO",
                        exit=False,
                    )
                    continue
                version = asic.get("target_graphics_version")
                if version is not None and version != self.get_arch():
                    console_error(
                        "profiling",
                        (
                            f"Switched GPU {identity} is {version}, not "
                            f"{self.get_arch()}; not restoring AUTO"
                        ),
                        exit=False,
                    )
                    continue
                self._set_perf_level(amdsmi, handle, level)

        self._with_amdsmi(_restore_auto)
        self._switched_perf_ids = []
