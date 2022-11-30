# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Combine, FallingEdge, Join, RisingEdge, Timer
from cocotb.types import LogicArray

from .nrzi_encode import nrzi_encode
from .nrzi_decode import nrzi_decode
from .pmd_dp83223_rx import check_bits
from .util import alist, compare_lists, print_list_at

@cocotb.test(timeout_time=3, timeout_unit='us')
async def test_loopback(pmd):
    rx_bits = [random.randrange(2) for _ in range(100)]
    tx_bits = [random.randrange(2) for _ in range(100)]

    pmd.loopback.value = 0
    pmd.signal_detect.value = 0
    pmd.tx_data.value = tx_bits[0]
    await Timer(1)
    await cocotb.start(Clock(pmd.clk_125, 8, units='ns').start())
    await cocotb.start(Clock(pmd.clk_250, 4, units='ns').start())
    
    async def send_rx():
        for bit in nrzi_encode(rx_bits):
            pmd.signal_detect.value = 1
            pmd.indicate_data.value = bit
            await Timer(8, units='ns')
        pmd.signal_detect.value = 0
        pmd.indicate_data.value = LogicArray('X')

    async def send_tx():
        for bit in tx_bits:
            pmd.tx_data.value = bit
            await FallingEdge(pmd.clk_125)

    async def recv_tx(delay):
        async def bits():
            await ClockCycles(pmd.clk_125, delay)
            for _ in range(len(tx_bits)):
                await RisingEdge(pmd.clk_125)
                yield pmd.request_data.value

        compare_lists(tx_bits, await alist(nrzi_decode(bits())))

    async def test_normal(delay=2):
        await cocotb.start(send_rx())
        await cocotb.start(send_tx())
        rx_task = await cocotb.start(check_bits(pmd, rx_bits))
        tx_task = await cocotb.start(recv_tx(delay))

        await Combine(Join(rx_task), Join(tx_task))

    await test_normal()

    async def loopback_monitor():
        await ClockCycles(pmd.clk_125, 2)
        while pmd.loopback.value:
            assert not pmd.request_data.value
            await RisingEdge(pmd.clk_125)

    tx_task = await cocotb.start(send_rx())
    await cocotb.start(send_tx())
    rx_task = await cocotb.start(check_bits(pmd, tx_bits))
    loop_task = await cocotb.start(loopback_monitor())
    pmd.loopback.value = 1

    await Join(tx_task)
    pmd.loopback.value = 0
    await Join(rx_task)
    loop_task.kill()

    await test_normal(1)
