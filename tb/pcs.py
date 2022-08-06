# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import enum
import random
import itertools

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Edge, RisingEdge, FallingEdge, Timer
from cocotb.types import LogicArray

from .util import alist, classproperty, ReverseList

class Code(enum.Enum):
    _0 = (0b11110, '0')
    _1 = (0b01001, '1')
    _2 = (0b10100, '2')
    _3 = (0b10101, '3')
    _4 = (0b01010, '4')
    _5 = (0b01011, '5')
    _6 = (0b01110, '6')
    _7 = (0b01111, '7')
    _8 = (0b10010, '8')
    _9 = (0b10011, '9')
    _A = (0b10110, 'A')
    _B = (0b10111, 'B')
    _C = (0b11010, 'C')
    _D = (0b11011, 'D')
    _E = (0b11100, 'E')
    _F = (0b11101, 'F')
    _I = (0b11111, 'I')
    _J = (0b11000, 'J')
    _K = (0b10001, 'K')
    _T = (0b01101, 'T')
    _R = (0b00111, 'R')
    _H = (0b00100, 'H')
    _V0 = (0b00000, 'V')
    _V1 = (0b00001, 'V')
    _V2 = (0b00010, 'V')
    _V3 = (0b00011, 'V')
    _V4 = (0b00101, 'V')
    _V5 = (0b00110, 'V')
    _V6 = (0b01000, 'V')
    _V7 = (0b01100, 'V')
    _V8 = (0b10000, 'V')
    _V9 = (0b11001, 'V')

    @classmethod
    def _missing_(cls, value):
        return cls.__members__['_' + value]

    @classmethod
    def decode(cls, bits):
        value = 0
        for bit in bits:
            value = (value << 1) | bit
        return cls(value)

    @classproperty
    def encode(cls):
        if not hasattr(cls, '_encode'):
            cls._encode = { data: cls(f"{data:X}") for data in range(16) }
        return cls._encode

    def __new__(cls, code, name):
        self = object.__new__(cls)
        self._value_ = code
        return self

    def __init__(self, code, name):
        self._name_ = name
        try:
            self.data = int(name, 16)
        except ValueError:
            self.data = None

    def __hash__(self):
        return hash(self.value)

    def __int__(self):
        if self.data is None:
            raise ValueError
        return self.data

    def __index__(self):
        return self._value_

    def __repr__(self):
        return f"{self.__class__.__name__}({self._value_:#07b}, '{self.name}')"

    def __str__(self):
        return f"/{self._name_}/"

    def __iter__(self):
        code = self.value
        for _ in range(5):
            yield (code & 0x10) >> 4
            code <<= 1

def as_nibbles(data):
    for byte in data:
       yield byte >> 4
       yield byte & 0xf

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
        as_codes(data[2:]),
        (Code('T'), Code('R')),
    )

async def mii_send_packet(pcs, nibbles):
    await FallingEdge(pcs.tx_ce)
    for nibble in nibbles:
        pcs.tx_en.value = 1
        pcs.tx_er.value = 0
        if nibble is None:
            pcs.tx_er.value = 1
        else:
            pcs.txd.value = nibble
        await FallingEdge(pcs.tx_ce)

    pcs.tx_en.value = 0
    pcs.tx_er.value = 0
    pcs.txd.value = LogicArray("XXXX")
    await FallingEdge(pcs.tx_ce)

async def mii_recv_packet(pcs):
    while not (pcs.rx_ce.value and pcs.rx_dv.value):
        await RisingEdge(pcs.rx_clk)

    while pcs.rx_dv.value:
        if pcs.rx_ce.value:
            if pcs.rx_er.value:
                yield None
            else:
                yield pcs.rxd.value
        await RisingEdge(pcs.rx_clk)

class PCSError(Exception):
    pass

class BadSSD(PCSError):
    pass

class PrematureEnd(PCSError):
    pass

async def pcs_recv_packet(pcs):
    rx_bits = ReverseList([1] * 10)

    async def read_bit():
        await RisingEdge(pcs.tx_clk)
        rx_bits.append(pcs.pma_data_tx.value)

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

async def pcs_send_codes(pcs, codes):
    await FallingEdge(pcs.rx_clk)
    codes = list(codes)
    bits = itertools.chain(*codes)
    try:
        while True:
            #valid = 2
            valid = random.randrange(3)
            pcs.pma_data_rx_valid.value = valid
            if valid == 0:
                data = 'XX'
            elif valid == 1:
                data = (next(bits), 'X')
            else:
                first = next(bits)
                try:
                    second = next(bits)
                except StopIteration:
                    second = 'X'
                data = (first, second)
            pcs.pma_data_rx.value = LogicArray(data)
            await FallingEdge(pcs.rx_clk)
    except StopIteration:
        pass

    pcs.pma_data_rx_valid.value = 1
    pcs.pma_data_rx.value = LogicArray('1X')

@cocotb.test(timeout_time=10, timeout_unit='us')
async def test_tx(pcs):
    async def tx_ce():
        pcs.tx_ce.value = 1
        while True:
            await ClockCycles(pcs.tx_clk, 1, False)
            pcs.tx_ce.value = 0
            await ClockCycles(pcs.tx_clk, 4, False)
            pcs.tx_ce.value = 1

    pcs.tx_en.value = 0
    pcs.tx_er.value = 0
    pcs.txd.value = LogicArray("XXXX")
    pcs.link_status.value = 1
    await cocotb.start(tx_ce())
    await Timer(1)
    await cocotb.start(Clock(pcs.tx_clk, 8, units='ns').start())
    await FallingEdge(pcs.tx_ce)

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

@cocotb.test(timeout_time=10, timeout_unit='us')
async def test_rx(pcs):
    pcs.pma_data_rx.value = LogicArray('11')
    pcs.pma_data_rx_valid.value = 2
    pcs.link_status.value = 1
    await Timer(1)
    await cocotb.start(Clock(pcs.rx_clk, 8, units='ns').start())

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
    )))

    assert packet == await alist(mii_recv_packet(pcs))

    for _ in range(3):
        while not (pcs.receiving.value and pcs.rx_er.value and pcs.rx_ce.value):
            await RisingEdge(pcs.rx_clk)
        assert pcs.rxd.value == 0xE
        await FallingEdge(pcs.receiving)

    assert [0x5, 0x5, None] == await alist(mii_recv_packet(pcs))

    # Test packet spacing
    for _ in range(10):
        assert [0x5, 0x5] == await alist(mii_recv_packet(pcs))
