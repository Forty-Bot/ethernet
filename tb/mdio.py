# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Edge, FallingEdge, First, RisingEdge, Timer
from cocotb.types import LogicArray

from .util import ClockEnable

def to_bits(val, width):
    for bit in range(width - 1, -1, -1):
        yield (val >> bit) & 1

def frame(phyad, regad, data=None, *, st=0b01, op=None, preamble_bits=32):
    for _ in range(preamble_bits):
        yield 1

    yield from to_bits(st, 2)
    if op is None:
        op = 0b10 if data is None else 0b01
    yield from to_bits(op, 2)

    yield from to_bits(phyad, 5)
    yield from to_bits(regad, 5)
    if data is None:
        return

    yield 1
    yield 0
    yield from to_bits(data, 16)

# Should be 50, but reduced to simulate faster
MDIO_RATIO = 3

async def mdio_read(mdio, phyad, regad, **kwargs):
    ret = 0

    for bit in frame(phyad, regad, **kwargs):
        await RisingEdge(mdio.ce)
        mdio.mdi.value = bit
        await FallingEdge(mdio.ce)
        mdio.mdi.value = LogicArray('X')

    for bit in range(19):
        await RisingEdge(mdio.ce)
        await RisingEdge(mdio.clk)
        
        if bit < 2:
            continue

        if bit == 2:
            if not mdio.mdo_valid.value:
                ret = None
            continue

        if ret is None:
            assert not mdio.mdo_valid.value
            continue
        else:
            assert mdio.mdo_valid.value

        ret <<= 1
        ret |= mdio.mdo.value

    return ret

async def mdio_write(mdio, phyad, regad, data, **kwargs):
    for bit in frame(phyad, regad, data, **kwargs):
        await RisingEdge(mdio.ce)
        mdio.mdi.value = bit
        await FallingEdge(mdio.ce)
        mdio.mdi.value = LogicArray('X')

async def wb_read(signals, addr, data):
    while not (signals['cyc'].value and signals['stb'].value):
        await FallingEdge(signals['clk'])

    assert not signals['we'].value
    assert signals['addr'].value == addr
    signals['data_read'].value = data
    signals['ack'].value = 1

    await RisingEdge(signals['clk'])
    signals['ack'].value = 0
    signals['data_read'].value = LogicArray('X' * 16)

    await FallingEdge(signals['clk'])
    assert not signals['stb'].value

async def wb_write(signals, addr, data):
    while not (signals['cyc'].value and signals['stb'].value):
        await FallingEdge(signals['clk'])

    signals['ack'].value = 1

    await RisingEdge(signals['clk'])
    assert signals['we'].value
    assert signals['addr'].value == addr
    assert signals['data_write'].value == data
    signals['ack'].value = 0

    await FallingEdge(signals['clk'])
    assert not signals['stb'].value

async def wb_err(signals):
    while not (signals['cyc'].value and signals['stb'].value):
        await FallingEdge(signals['clk'])

    signals['err'].value = 1
    await RisingEdge(signals['clk'])
    signals['err'].value = 0
    await FallingEdge(signals['clk'])
    assert not signals['stb'].value

async def setup(mdio):
    mdio.mdi.value = 0
    mdio.ack.value = 0
    mdio.err.value = 0
    mdio.data_read.value = LogicArray('X' * 16)
    await cocotb.start(ClockEnable(mdio.clk, mdio.ce, MDIO_RATIO))
    await Timer(1)
    await cocotb.start(Clock(mdio.clk, 8, units='ns').start())

def mdio_signals(mdio):
    return {
        'clk': mdio.clk,
        'ack': mdio.ack,
        'err': mdio.err,
        'cyc': mdio.cyc,
        'stb': mdio.stb,
        'we': mdio.we,
        'addr': mdio.addr,
        'data_write': mdio.data_write,
        'data_read': mdio.data_read,
    }

@cocotb.test(timeout_time=50, timeout_unit='us')
async def test_mdio(mdio):
    await setup(mdio)

    reads = [(i, random.randrange(0, 0xFFFF)) for i in range(16)]
    writes = [(i, random.randrange(0, 0xFFFF)) for i in range(16)]
    random.shuffle(reads)
    random.shuffle(writes)

    async def rw_mdio():
        for (read, write) in zip(reads, writes):
            assert await mdio_read(mdio, 0, read[0]) == read[1]
            await mdio_write(mdio, 0, write[0], write[1])
    await cocotb.start(rw_mdio())

    signals = mdio_signals(mdio)
    for (read, write) in zip(reads, writes):
        await wb_read(signals, read[0], read[1])
        await wb_write(signals, write[0], write[1])

@cocotb.test(timeout_time=20, timeout_unit='us')
async def test_badmdio(mdio):
    await setup(mdio)

    async def nowb():
        await First(RisingEdge(mdio.cyc), RisingEdge(mdio.stb))
        assert False, "Unexpected wishbone transaction"
    await cocotb.start(nowb())

    # Force mdi low to ensure we get exactly 31 bits in the preamble
    async def rw_mdio(phyad, **kwargs):
        mdio.mdi.value = 0
        await FallingEdge(mdio.clk)
        assert await mdio_read(mdio, phyad, 0, **kwargs) is None
        mdio.mdi.value = 0
        await FallingEdge(mdio.clk)
        await mdio_write(mdio, phyad, 0, 0, **kwargs)

    await rw_mdio(0, preamble_bits=31)
    await rw_mdio(0, st=0b00)
    await rw_mdio(0, op=0b00)
    await rw_mdio(1)
    await rw_mdio(0x10)

@cocotb.test(timeout_time=20, timeout_unit='us')
async def test_badwb(mdio):
    await setup(mdio)
    signals = mdio_signals(mdio)

    async def bad_resp():
        # No ack
        await ClockCycles(mdio.stb, 2, False)
        # Error response
        for _ in range(2):
            await wb_err(signals)

    await cocotb.start(bad_resp())

    for _ in range(2):
        assert await mdio_read(mdio, 0, 0) is None
        await mdio_write(mdio, 0, 0, 0)
