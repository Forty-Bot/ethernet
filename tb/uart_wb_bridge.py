# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import Event, FallingEdge, Timer

from .axis_wb_bridge import Encoder, STATUS_WE
from .mdio import wb_read, wb_write, wb_err
from .uart_rx import putchar, BIT_STEPS
from .uart_tx import getchar

@cocotb.test(timeout_time=100, timeout_unit='us')
async def test_bridge(bridge):
    bridge.clk.value = BinaryValue('Z')
    bridge.rst.value = 1
    bridge.rx.value = 1
    bridge.wb_ack.value = 0
    bridge.wb_err.value = 0
    bridge.high_speed.value = 1

    await Timer(1)
    bridge.rst.value = 0
    await cocotb.start(Clock(bridge.clk, 8, units='ns').start())
    await FallingEdge(bridge.clk)

    wb = {
        'clk': bridge.clk,
        'ack': bridge.wb_ack,
        'err': bridge.wb_err,
        'cyc': bridge.wb_cyc,
        'stb': bridge.wb_stb,
        'we': bridge.wb_we,
        'addr': bridge.wb_addr,
        'data_write': bridge.wb_data_write,
        'data_read': bridge.wb_data_read,
    }

    e = Encoder()
    recv_ready = Event()

    async def send_break():
        bridge.rx.value = 0
        await Timer(BIT_STEPS * 20)
        bridge.rx.value = 1
        await Timer(BIT_STEPS)

    async def send():
        for c in e.encode(0x0123, 0x4567):
            await putchar(bridge.rx, c)

        # Start a read
        await recv_ready.wait()
        await putchar(bridge.rx, e.encode(0xdead)[0])
        # Cancel it
        await send_break()

        # And do another read
        e.last_addr = None
        for c in e.encode(0x89ab):
            await putchar(bridge.rx, c)

    await cocotb.start(send())
    await cocotb.start(wb_write(wb, 0x0123, 0x4567))

    uart = {
        'clk': bridge.clk,
        'tx': bridge.tx,
    }

    assert await getchar(uart) == STATUS_WE

    recv_ready.set()
    await cocotb.start(wb_read(wb, 0x89ab, 0xcdef))

    assert await getchar(uart) == 0
    assert await getchar(uart) == 0xcd
    assert await getchar(uart) == 0xef
