# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import FallingEdge, Timer
from cocotb.utils import get_sim_time, get_sim_steps

from .axis_replay_buffer import send_packet
from .util import timeout

BAUD = 4e6
BIT_STEPS = get_sim_steps(1 / BAUD, 'sec', round_mode='round')

async def getchar(signals):
    while not signals['tx'].value:
        await FallingEdge(signals['clk'])
    while signals['tx'].value:
        await FallingEdge(signals['clk'])
    await Timer(BIT_STEPS // 2)

    result = 0
    for _ in range(8):
        await Timer(BIT_STEPS)
        result >>= 1
        result |= 0x80 if signals['tx'].value else 0

    await Timer(BIT_STEPS)
    assert signals['tx'].value
    return result

@timeout(50, 'us')
async def test_tx(uart, ratio):
    uart.clk.value = BinaryValue('Z')
    uart.rst.value = 1
    uart.valid.value = 0
    uart.high_speed.value = BAUD == 4e6

    await Timer(1)
    uart.rst.value = 0
    await cocotb.start(Clock(uart.clk, 8, units='ns').start())
    await FallingEdge(uart.clk)

    msg = b"Hello"

    axis = {
        'clk': uart.clk,
        'data': uart.data,
        'valid': uart.valid,
        'ready': uart.ready,
    }

    await cocotb.start(send_packet(axis, msg, ratio))

    then = get_sim_time()
    for c in msg:
        assert c == await getchar({
            'clk': uart.clk,
            'tx': uart.tx,
        })
    now = get_sim_time()

    expected = BIT_STEPS * (10 * len(msg) - 0.5)
    actual = now - then
    assert abs(actual - expected) / expected < 0.01

uart_tests = TestFactory(test_tx)
uart_tests.add_option('ratio', (1, int(125e6 / BAUD * 10)))
uart_tests.generate_tests()
