# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import itertools
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Event, FallingEdge, RisingEdge, Timer
from cocotb.types import LogicArray

from .scramble import descramble
from .descramble import scramble
from .pcs_tx import as_nibbles, mii_send_packet, pcs_recv_packet
from .pcs_rx import frame, mii_recv_packet
from .util import alist, ClockEnable

@cocotb.test(timeout_time=15, timeout_unit='us')
async def test_transfer(phy):
    phy.coltest.value = 0
    phy.descrambler_test_mode.value = 0
    phy.tx_en.value = 0
    phy.rx_data_valid.value = 0
    phy.signal_status.value = 0
    phy.loopback.value = 0
    phy.link_monitor_test_mode.value = 1
    await cocotb.start(ClockEnable(phy.clk, phy.tx_ce, 5))
    await Timer(1)
    phy.signal_status.value = 1
    await cocotb.start(Clock(phy.clk, 8, units='ns').start())
    await FallingEdge(phy.tx_ce)

    tx_data = list(as_nibbles([0x55, 0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef]))
    rx_data = list(as_nibbles((0x55, 0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54, 0x32, 0x10)))

    async def send_rx_packets():
        def rx_bits():
            packet_bits = list(itertools.chain.from_iterable(frame(rx_data)))

            # First packet is OK, second is a collision
            yield from itertools.repeat(1, 120)
            yield from packet_bits
            yield from itertools.repeat(1, 240)
            yield from packet_bits

            while not phy.loopback.value:
                yield 1

        for bit in scramble(rx_bits()):
            phy.rx_data.value = LogicArray((bit, 'X'))
            phy.rx_data_valid.value = 1
            await FallingEdge(phy.clk)

    async def send_tx_packets():
        signals = {
            'ce': phy.tx_ce,
            'enable': phy.tx_en,
            'err': phy.tx_er,
            'data': phy.txd,
        }

        # Send a packet, and then cause a collision
        await ClockCycles(phy.clk, 240)
        await mii_send_packet(phy, tx_data, signals)
        await ClockCycles(phy.clk, 120)
        await mii_send_packet(phy, tx_data, signals)

        while not phy.loopback.value:
            await FallingEdge(phy.clk)

        # Loopback
        await ClockCycles(phy.clk, 120)
        await mii_send_packet(phy, tx_data, signals)

        # Collision test
        await ClockCycles(phy.clk, 120)
        phy.coltest.value = 1
        await mii_send_packet(phy, tx_data, signals)
        
        while phy.loopback.value:
            await FallingEdge(phy.clk)

        await ClockCycles(phy.clk, 240)
        await mii_send_packet(phy, tx_data, signals)

    async def loopback():
        while phy.loopback.value:
            phy.rx_data.value = LogicArray((int(phy.tx_data.value), 'X'))
            await FallingEdge(phy.clk)

    await cocotb.start(send_tx_packets())
    await cocotb.start(send_rx_packets())

    rx_ready = Event()
    tx_ready = Event()

    async def recv_rx_packets():
        async def packets():
            while True:
                yield await alist(mii_recv_packet(phy, {
                    'ce': phy.rx_ce,
                    'err': phy.rx_er,
                    'data': phy.rxd,
                    'valid': phy.rx_dv,
                }))
    
        packets = packets()
        assert rx_data == await anext(packets)
        assert rx_data == await anext(packets)
        rx_ready.set()
        assert tx_data == await anext(packets)
        assert tx_data == await anext(packets)
        rx_ready.set()
        assert rx_data == await anext(packets)
        rx_ready.set()

    async def recv_tx_packets():
        async def recv():
            while True:
                await RisingEdge(phy.clk)
                yield phy.tx_data.value

        async def packets():
            while True:
                yield await alist(pcs_recv_packet(phy, descramble(recv())))

        packets = packets()
        assert tx_data == await anext(packets)
        assert tx_data == await anext(packets)
        tx_ready.set()
        assert tx_data == await anext(packets)
        assert tx_data == await anext(packets)
        tx_ready.set()
        assert tx_data == await anext(packets)
        tx_ready.set()

    await cocotb.start(recv_rx_packets())
    await cocotb.start(recv_tx_packets())

    crs = 0
    col = 0

    async def count_crs():
        nonlocal crs
        while True:
            await RisingEdge(phy.crs)
            crs += 1
            await FallingEdge(phy.crs)

    async def count_col():
        nonlocal col
        while True:
            await RisingEdge(phy.col)
            col += 1
            await FallingEdge(phy.col)

    await cocotb.start(count_crs())
    await cocotb.start(count_col())

    await rx_ready.wait()
    await tx_ready.wait()
    assert crs == 3
    assert col == 1
    rx_ready.clear()
    tx_ready.clear()

    phy.loopback.value = 1
    await ClockCycles(phy.clk, 1)
    await cocotb.start(loopback())

    await rx_ready.wait()
    await tx_ready.wait()
    assert crs == 5
    assert col == 2
    rx_ready.clear()
    tx_ready.clear()

    await FallingEdge(phy.clk)
    phy.loopback.value = 0
    phy.coltest.value = 0
    await cocotb.start(send_rx_packets())

    await rx_ready.wait()
    await tx_ready.wait()
    assert crs == 7
    assert col == 2
