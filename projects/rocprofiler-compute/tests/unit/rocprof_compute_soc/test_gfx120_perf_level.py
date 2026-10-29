# Copyright (c) Advanced Micro Devices, Inc.
# SPDX-License-Identifier:  MIT

"""Gfx120 perf-level setup uses a fake amdsmi module and does not touch a GPU."""

import argparse
from types import SimpleNamespace

import pytest

from rocprof_compute_soc.gfx120_common import Gfx120SoC
from utils.specs import MachineSpecs


class _PerfLevel:
    STABLE_STD = "STABLE_STD"
    AUTO = "AUTO"


def _processor(name, version, serial, device_id):
    return {
        "handle": SimpleNamespace(name=name),
        "target_graphics_version": version,
        "asic_serial": serial,
        "device_id": device_id,
    }


class FakeAmdsmi:
    """Stand-in for the amdsmi module. Records calls and never opens a device."""

    def __init__(self, processors, fail_stable=()):
        self.processors = list(processors)
        self.fail_stable = list(fail_stable)
        self.AmdSmiDevPerfLevel = _PerfLevel
        self.init_count = 0
        self.shutdown_count = 0
        self.sets = []

    def amdsmi_init(self):
        self.init_count += 1

    def amdsmi_shut_down(self):
        self.shutdown_count += 1

    def amdsmi_get_processor_handles(self):
        return [proc["handle"] for proc in self.processors]

    def amdsmi_get_gpu_asic_info(self, handle):
        for proc in self.processors:
            if proc["handle"] == handle:
                return {
                    "target_graphics_version": proc["target_graphics_version"],
                    "asic_serial": proc["asic_serial"],
                    "device_id": proc["device_id"],
                }
        raise KeyError(handle)

    def amdsmi_set_gpu_perf_level(self, handle, level):
        if level == _PerfLevel.STABLE_STD and handle in self.fail_stable:
            raise RuntimeError(f"rejected STABLE_STD for {handle}")
        self.sets.append((handle, level))


def _soc(arch):
    soc = Gfx120SoC(
        argparse.Namespace(no_roof=True),
        MachineSpecs(),
        arch=arch,
        l2_banks=32,
        pipes_per_gpu=4,
    )
    soc.perfmon_filter = lambda: ["filtered"]
    return soc


def _install(monkeypatch, fake):
    monkeypatch.setattr(
        "utils.amdsmi_interface.import_amdsmi_module",
        lambda: fake,
    )
    return fake


@pytest.fixture
def fake_amdsmi(monkeypatch):
    # Two gfx1201 boards share a device id. Serials keep them distinct.
    # gfx1100 sits between them so an index restore would pick it after reorder.
    return _install(
        monkeypatch,
        FakeAmdsmi(
            (
                _processor("r9700", "gfx1201", "SN-A", 0x7551),
                _processor("w7900", "gfx1100", "SN-W", 0x744C),
                _processor("r9700-b", "gfx1201", "SN-B", 0x7551),
            )
        ),
    )


def _handles_at(fake, level):
    return [handle for handle, set_level in fake.sets if set_level == level]


def test_matcher_sets_stable_std_only_on_this_arch(fake_amdsmi):
    soc = _soc("gfx1201")
    assert soc.profiling_setup() == ["filtered"]

    gfx1201 = [
        proc["handle"]
        for proc in fake_amdsmi.processors
        if proc["target_graphics_version"] == "gfx1201"
    ]
    assert _handles_at(fake_amdsmi, _PerfLevel.STABLE_STD) == gfx1201
    w7900 = fake_amdsmi.processors[1]["handle"]
    assert w7900 not in _handles_at(fake_amdsmi, _PerfLevel.STABLE_STD)
    assert soc._switched_perf_ids == [
        ("asic_serial", "SN-A"),
        ("asic_serial", "SN-B"),
    ]
    assert fake_amdsmi.init_count == 1
    assert fake_amdsmi.shutdown_count == 1

    soc.post_profiling()
    assert _handles_at(fake_amdsmi, _PerfLevel.AUTO) == gfx1201
    assert fake_amdsmi.init_count == 2
    assert soc._switched_perf_ids == []


def test_restore_finds_same_arch_gpus_after_reorder(fake_amdsmi):
    soc = _soc("gfx1201")
    soc.profiling_setup()
    first, w7900, second = (proc["handle"] for proc in fake_amdsmi.processors)

    # Former switched indexes 0 and 2 are now the W7900 and the first R9700.
    fake_amdsmi.processors = [
        fake_amdsmi.processors[1],
        fake_amdsmi.processors[2],
        fake_amdsmi.processors[0],
    ]
    soc.post_profiling()

    assert _handles_at(fake_amdsmi, _PerfLevel.AUTO) == [first, second]
    assert w7900 not in _handles_at(fake_amdsmi, _PerfLevel.AUTO)


def test_restore_uses_device_id_when_serial_is_missing(monkeypatch):
    no_serial = _processor("r9700", "gfx1201", "N/A", 0x7551)
    blank_serial = _processor("r9700-b", "gfx1201", "  ", 0x7550)
    other = _processor("w7900", "gfx1100", None, 0x744C)
    fake = _install(
        monkeypatch,
        FakeAmdsmi((no_serial, other, blank_serial)),
    )
    soc = _soc("gfx1201")
    soc.profiling_setup()
    assert soc._switched_perf_ids == [
        ("device", 0x7551, "gfx1201"),
        ("device", 0x7550, "gfx1201"),
    ]

    fake.processors = [blank_serial, no_serial, other]
    soc.post_profiling()
    assert _handles_at(fake, _PerfLevel.AUTO) == [
        no_serial["handle"],
        blank_serial["handle"],
    ]
    assert other["handle"] not in _handles_at(fake, _PerfLevel.AUTO)


def test_gfx1100_soc_does_not_switch_gfx1201(fake_amdsmi):
    soc = _soc("gfx1100")
    soc.profiling_setup()
    w7900 = fake_amdsmi.processors[1]["handle"]
    assert fake_amdsmi.sets == [(w7900, _PerfLevel.STABLE_STD)]
    soc.post_profiling()
    assert fake_amdsmi.sets[-1] == (w7900, _PerfLevel.AUTO)


def test_failed_stable_std_is_logged_and_not_restored(fake_amdsmi, caplog):
    failed = fake_amdsmi.processors[0]["handle"]
    kept = fake_amdsmi.processors[2]["handle"]
    w7900 = fake_amdsmi.processors[1]["handle"]
    fake_amdsmi.fail_stable.append(failed)

    soc = _soc("gfx1201")
    with caplog.at_level("ERROR"):
        assert soc.profiling_setup() == ["filtered"]

    assert (failed, _PerfLevel.STABLE_STD) not in fake_amdsmi.sets
    assert (kept, _PerfLevel.STABLE_STD) in fake_amdsmi.sets
    assert soc._switched_perf_ids == [("asic_serial", "SN-B")]
    assert "rejected STABLE_STD" in caplog.text

    # Index 0 after this reorder is the GPU whose STABLE_STD failed.
    fake_amdsmi.processors = [
        fake_amdsmi.processors[0],
        fake_amdsmi.processors[2],
        fake_amdsmi.processors[1],
    ]
    caplog.clear()
    with caplog.at_level("ERROR"):
        soc.post_profiling()

    assert _handles_at(fake_amdsmi, _PerfLevel.AUTO) == [kept]
    assert failed not in _handles_at(fake_amdsmi, _PerfLevel.AUTO)
    assert w7900 not in _handles_at(fake_amdsmi, _PerfLevel.AUTO)
    assert "rejected STABLE_STD" not in caplog.text


def test_unavailable_amdsmi_skips_perf_level(monkeypatch, caplog):
    monkeypatch.setattr(
        "utils.amdsmi_interface.import_amdsmi_module",
        lambda: None,
    )
    soc = _soc("gfx1201")
    with caplog.at_level("ERROR"):
        assert soc.profiling_setup() == ["filtered"]
    assert soc._switched_perf_ids == []
    assert "amdsmi is unavailable" in caplog.text
    soc.post_profiling()
