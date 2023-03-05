# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, Timer

@cocotb.test(timeout_time=100, timeout_unit='us')
async def test_bridge(sync):
    sync.clk.value = BinaryValue('Z')
    sync.rst_in.value = 0

    await Timer(1)
    assert sync.rst_out.value
    await cocotb.start(Clock(sync.clk, 8, units='ns').start())

    await RisingEdge(sync.clk)
    assert sync.rst_out.value

    await RisingEdge(sync.clk)
    assert sync.rst_out.value

    await RisingEdge(sync.clk)
    assert not sync.rst_out.value

    await Timer(1)
    assert not sync.rst_out.value
    sync.rst_in.value = 1

    await ReadOnly()
    assert sync.rst_out.value

    await Timer(1)
    sync.rst_in.value = 0
    assert sync.rst_out.value

    await RisingEdge(sync.clk)
    assert sync.rst_out.value

    await RisingEdge(sync.clk)
    assert sync.rst_out.value

    await RisingEdge(sync.clk)
    assert not sync.rst_out.value
