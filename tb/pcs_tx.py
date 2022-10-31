# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge, Timer
from cocotb.types import LogicArray

from .pcs import Code, as_nibbles
from .util import alist, ClockEnable, ReverseList

async def mii_send_packet(pcs, nibbles):
    await FallingEdge(pcs.ce)
    for nibble in nibbles:
        pcs.enable.value = 1
        pcs.err.value = 0
        if nibble is None:
            pcs.err.value = 1
        else:
            pcs.data.value = nibble
        await FallingEdge(pcs.ce)

    pcs.enable.value = 0
    pcs.err.value = 0
    pcs.data.value = LogicArray("XXXX")
    await FallingEdge(pcs.ce)

class PCSError(Exception):
    pass

class BadSSD(PCSError):
    pass

class PrematureEnd(PCSError):
    pass

async def pcs_recv_bits(pcs, data=None):
    if data is None:
        data = pcs.bits

    while True:
        await RisingEdge(pcs.clk)
        yield data.value

async def pcs_recv_packet(pcs, bits=None):
    if bits is None:
        bits = pcs_recv_bits(pcs)

    rx_bits = ReverseList([1] * 10)

    async def read_bit():
        rx_bits.append(await anext(bits))

    async def read_code():
        for _ in range(5):
            await read_bit()

    async def bad_ssd():
        while not all(rx_bits[9:0]):
            await read_bit()
        raise BadSSDError()

    while all(rx_bits[9:2]) or rx_bits[0]:
        await read_bit()

    if Code.decode(rx_bits[9:5]) != Code('I') or \
       Code.decode(rx_bits[4:0]) != Code('J'):
        await bad_ssd()

    await read_code()
    if Code.decode(rx_bits[4:0]) != Code('K'):
        await bad_ssd()

    yield 0x5
    await read_code()

    yield 0x5
    while any(rx_bits[9:0]):
        await read_code()
        code = Code.decode(rx_bits[9:5])
        if code == Code('T') and Code.decode(rx_bits[4:0]) == Code('R'):
            return
        yield code.data
    raise PrematureEndError()

@cocotb.test(timeout_time=10, timeout_unit='us')
async def test_tx(pcs):
    pcs.enable.value = 0
    pcs.err.value = 0
    pcs.data.value = LogicArray("XXXX")
    pcs.link_status.value = 1
    await cocotb.start(ClockEnable(pcs.clk, pcs.ce, 5))
    await Timer(1)
    await cocotb.start(Clock(pcs.clk, 8, units='ns').start())
    await FallingEdge(pcs.ce)

    # Test that all bytes can be transmitted
    packet = list(as_nibbles((0x55, 0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF)))
    # And ensure errors are propagated
    packet.insert(10, None)
    await cocotb.start(mii_send_packet(pcs, packet))
    assert packet == await alist(pcs_recv_packet(pcs))

    # Test start errors
    await cocotb.start(mii_send_packet(pcs, [None]))
    assert [0x5, 0x5, None] == await alist(pcs_recv_packet(pcs))
    await cocotb.start(mii_send_packet(pcs, [0x5, None]))
    assert [0x5, 0x5, None] == await alist(pcs_recv_packet(pcs))
