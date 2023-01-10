# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import itertools

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer
from cocotb.types import LogicArray

from .pcs import Code, as_nibbles
from .util import alist, send_recovered_bits, timeout, with_valids

def as_codes(nibbles):
    for nibble in nibbles:
        if nibble is None:
            yield Code('H')
        else:
            yield Code.encode[nibble]

def frame(data):
    return itertools.chain(
        (Code('J'), Code('K')),
        # Chop off the SSD
        as_codes(itertools.islice(data, 2, None)),
        (Code('T'), Code('R')),
    )

async def mii_recv_packet(pcs, signals=None):
    if signals is None:
        signals = {
            'ce': pcs.ce,
            'err': pcs.err,
            'data': pcs.data,
            'valid': pcs.valid,
        }

    while not (signals['ce'].value and signals['valid'].value):
        await RisingEdge(pcs.clk)

    while signals['valid'].value:
        if signals['ce'].value:
            if 'err' in signals and signals['err'].value:
                yield None
            else:
                yield signals['data'].value
        await RisingEdge(pcs.clk)

async def pcs_send_codes(pcs, codes, valids):
    await send_recovered_bits(pcs.clk, pcs.bits, pcs.bits_valid,
                              itertools.chain(*codes), valids)

@timeout(10, 'us')
async def test_rx(pcs, valids):
    pcs.bits.value = LogicArray('11')
    pcs.bits_valid.value = 2
    pcs.link_status.value = 1
    await Timer(1)
    await cocotb.start(Clock(pcs.clk, 8, units='ns').start())

    packet = list(as_nibbles((0x55, 0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF)))
    # And test errors too
    packet.insert(10, None)

    await cocotb.start(pcs_send_codes(pcs, itertools.chain(
        frame(packet),
        # Bad SSDs
        (Code('C'), Code('I'), Code('I')),
        (Code('J'), Code('I'), Code('I')),
        (Code('J'), Code('H'), Code('I'), Code('I')),
        # Premature end, plus two clocks since we don't have instant turnaround
        (Code('J'), Code('K'), Code('I'), Code('I'), (1,1)),
        # Packet spacing
        *((*frame([0x55, 0x55]), (1,) * i) for i in range(10))
    ), valids))

    assert packet == await alist(mii_recv_packet(pcs))

    false_carriers = 0
    for _ in range(3):
        while not (pcs.rx.value and pcs.err.value and pcs.ce.value):
            await RisingEdge(pcs.clk)
            false_carriers += pcs.false_carrier.value
        assert pcs.data.value == 0xE
        await FallingEdge(pcs.rx)
    assert false_carriers == 3

    assert [0x5, 0x5, None] == await alist(mii_recv_packet(pcs))

    # Test packet spacing
    for _ in range(10):
        assert [0x5, 0x5] == await alist(mii_recv_packet(pcs))

with_valids(globals(), test_rx)
