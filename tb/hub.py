# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import itertools

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Combine, FallingEdge, Join, RisingEdge, Timer
from cocotb.types import LogicArray

from .descramble import scramble
from .mdio_regs import BMSR, BMSR_LSTATUS, VCR, VCR_LTEST, wb_xfer
from .nrzi_encode import nrzi_encode
from .nrzi_decode import nrzi_decode
from .pcs_tx import as_nibbles, mii_send_packet, pcs_recv_packet
from .pcs_rx import frame, mii_recv_packet
from .scramble import descramble
from .util import BIT, alist

@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_hub(hub):
    hub.clk_125.value = BinaryValue('Z')
    hub.clk_250.value = BinaryValue('Z')
    hub.signal_detect.value = 0
    hub.wb_cyc.value = 1

    await Timer(1)
    await cocotb.start(Clock(hub.clk_125, 8, units='ns').start())
    await cocotb.start(Clock(hub.clk_250, 4, units='ns').start())

    wb = {
        'clk': hub.clk_125,
        'cyc': hub.wb_cyc,
        'stb': hub.wb_stb,
        'we': hub.wb_we,
        'addr': hub.wb_addr,
        'data_write': hub.wb_data_write,
        'data_read': hub.wb_data_read,
        'ack': hub.wb_ack,
        'err': hub.wb_err,
    }

    # Enable fast link stabilization for testing
    for i in range(4):
        await wb_xfer(wb, BIT(i + 5) + VCR, VCR_LTEST, delay=2)

    packet = list(as_nibbles((0x55, *b"Hello world!")))
    packet_bits = list(itertools.chain.from_iterable(frame(packet)))
    itertools.chain(itertools.repeat(1, 120), packet_bits, itertools.repeat(1))

    async def send_rx(i, bits):
        hub.signal_detect[i].value = 1
        for bit in nrzi_encode(scramble(bits)):
            hub.indicate_data[i].value = bit
            await Timer(8, units='ns')
        hub.signal_detect[i].value = 0
        hub.indicate_data[i].value = BinaryValue('X')

    async def recv_tx(i, packets):
        async def bits():
            await ClockCycles(hub.clk_125, 1)
            while True:
                await RisingEdge(hub.clk_125)
                yield hub.request_data[i].value

        data = descramble(nrzi_decode(bits()))
        for expected, valid in packets:
            actual = await alist(pcs_recv_packet(None, data))
            if valid:
                assert actual == expected
            else:
                assert actual != expected

    await cocotb.start(send_rx(0, itertools.chain(
        itertools.repeat(1, 120),
        packet_bits,
        itertools.repeat(1, 120),
        packet_bits,
        itertools.repeat(1),
    )))
    await cocotb.start(send_rx(1, itertools.chain(
        itertools.repeat(1, 300),
        packet_bits,
        itertools.repeat(1),
    )))
    await cocotb.start(send_rx(2, itertools.repeat(1)))
    await cocotb.start(send_rx(3, itertools.repeat(1)))

    receivers = [
            await cocotb.start(recv_tx(0, ((packet, False),))),
            await cocotb.start(recv_tx(1, ((packet, True), (packet, False)))),
            await cocotb.start(recv_tx(2, ((packet, True), (packet, False)))),
            await cocotb.start(recv_tx(3, ((packet, True), (packet, False)))),
    ]

    await Combine(*(Join(t) for t in receivers))

    for i in range(4):
        assert not await wb_xfer(wb, BIT(i + 5) + BMSR, delay=2) & BMSR_LSTATUS
        assert await wb_xfer(wb, BIT(i + 5) + BMSR, delay=2) & BMSR_LSTATUS
