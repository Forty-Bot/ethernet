# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer

from .pcs_rx import mii_recv_packet
from .pcs_tx import mii_send_packet
from .util import alist, ClockEnable, lookahead, timeout

@cocotb.test(timeout_time=50, timeout_unit='us')
async def test_elastic(buf):
    buf.clk.value = BinaryValue('Z')
    buf.tx_ce.value = 0
    buf.tx_en.value = 0
    buf.rx_ce.value = 0

    await Timer(1)
    await cocotb.start(Clock(buf.clk, 8, units='ns').start())
    await FallingEdge(buf.clk)
    await cocotb.start(ClockEnable(buf.clk, buf.tx_ce, 5))
    await FallingEdge(buf.clk)
    rx_ce = await cocotb.start(ClockEnable(buf.clk, buf.rx_ce, 5))

    underflows = 0
    overflows = 0

    async def count_excursions():
        nonlocal underflows, overflows
        while True:
            await RisingEdge(buf.clk)
            underflows += buf.underflow.value
            overflows += buf.overflow.value

    await cocotb.start(count_excursions())

    in_signals = {
        'ce': buf.tx_ce,
        'enable': buf.tx_en,
        'err': buf.tx_er,
        'data': buf.txd,
    }
    out_signals = {
        'ce': buf.rx_ce,
        'err': buf.rx_er,
        'data': buf.rxd,
        'valid': buf.rx_dv,
    }

    for packet in (list(range(10)), [0, 1, 2, None, 4, 5]):
        await cocotb.start(mii_send_packet(buf, packet, in_signals))
        assert packet == await alist(mii_recv_packet(buf, out_signals))

    packet = list(range(10))
    for ratio in (2, 12):
        rx_ce.kill()
        while not buf.tx_ce.value:
            await RisingEdge(buf.clk)
        rx_ce = await cocotb.start(ClockEnable(buf.clk, buf.rx_ce, ratio))

        underflows = 0
        overflows = 0
        await cocotb.start(mii_send_packet(buf, packet, in_signals))
        outs = await alist(mii_recv_packet(buf, out_signals))
        if ratio > 5:
            assert overflows
        else:
            assert underflows

        last = None
        for nibble in outs:
            if nibble is not None:
                try:
                    int(nibble)
                except:
                    raise
                assert nibble != last
            last = nibble

    packet = list(range(5))
    for ratio in (4, 6):
        # Wait for a CE before shutting it off; we need to output at least one idle
        while not buf.rx_ce.value:
            await FallingEdge(buf.clk)
        await FallingEdge(buf.clk)
        rx_ce.kill()

        underflows = 0
        overflows = 0
        await cocotb.start(mii_send_packet(buf, packet, in_signals))

        # Set up a worst-case scenario
        while not buf.rx_dv.value:
            await FallingEdge(buf.clk)
        if ratio == 6:
            await ClockCycles(buf.clk, 5, False)
        rx_ce = await cocotb.start(ClockEnable(buf.clk, buf.rx_ce, ratio))

        # And make sure everything works out
        assert packet == await alist(mii_recv_packet(buf, out_signals))
