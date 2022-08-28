# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Edge, FallingEdge, First, RisingEdge, Timer
from cocotb.types import LogicArray

from .util import ClockEnable

@cocotb.test(timeout_time=500, timeout_unit='ns')
async def test_io(io):
    io.tx_en.value = LogicArray('X')
    io.tx_er.value = LogicArray('X')
    io.txd.value = LogicArray('X' * 4)
    await Timer(1)
    await cocotb.start(Clock(io.clk, 8, units='ns').start())

    async def send_datum(enable, err, data):
        await RisingEdge(io.tx_clk)
        io.tx_en.value = LogicArray('X')
        io.tx_er.value = LogicArray('X')
        io.txd.value = LogicArray('X' * 4)
        await Timer(25, 'ns')
        io.tx_en.value = enable
        io.tx_er.value = err
        io.txd.value = data

    async def send_data():
        await send_datum(0, 1, 1)
        await send_datum(1, 0, 2)
        await send_datum(0, 1, 3)
        await send_datum(1, 0, 4)
        await send_datum(0, 1, 5)
    await cocotb.start(send_data())

    async def recv_datum(enable, err, data):
        await RisingEdge(io.ce)
        await RisingEdge(io.clk)
        assert io.ce.value
        assert io.enable.value == enable
        assert io.err.value == err
        assert io.data.value == data

    await recv_datum(0, 1, 1)
    await recv_datum(1, 0, 2)
    await recv_datum(0, 1, 3)
    await recv_datum(1, 0, 4)
    await recv_datum(0, 1, 5)
