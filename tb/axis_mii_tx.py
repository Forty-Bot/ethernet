# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import enum
import random
import zlib

import cocotb
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import ClockCycles, Edge, FallingEdge, First, RisingEdge, Timer
from cocotb.types import LogicArray
from cocotb.utils import get_sim_time

from . import axis_replay_buffer
from .pcs_rx import mii_recv_packet
from .util import alist, lookahead, timeout

import os

skip_slow = not os.environ.get('RUN_SLOW', False)

async def init(mac):
    mac.rst.value = 1
    mac.mii_col.value = 0
    mac.mii_crs.value = 0
    mac.axis_valid.value = 0
    mac.axis_err.value = 0
    mac.short_backoff.value = 1
    await Timer(1)
    mac.rst.value = 0
    await cocotb.start(Clock(mac.clk, 8, units='ns').start())
    await FallingEdge(mac.clk)

def send_packet(mac, packet, **kwargs):
    return axis_replay_buffer.send_packet({
        'clk': mac.clk,
        'data': mac.axis_data,
        'err': mac.axis_err,
        'valid': mac.axis_valid,
        'last': mac.axis_last,
        'ready': mac.axis_ready,
    }, packet, **kwargs)

class MACError(Exception):
    pass

class FrameCheckError(MACError):
    pass

class AlignmentError(MACError):
    pass

class PaddingError(MACError):
    pass

async def nibbles_to_bytes(nibbles):
    while True:
        try:
            lo = await anext(nibbles)
        except StopAsyncIteration:
            return

        try:
            hi = await anext(nibbles)
        except StopAsyncIteration:
            raise AlignmentError

        yield hi << 4 | lo

SFD = 0xd5

async def skip_preamble(packet):
    saw_ssd = False
    async for byte in packet:
        if saw_ssd:
            yield byte
        elif byte == SFD:
            saw_ssd = True

FCS_GOOD = zlib.crc32(b'\0\0\0\0')

async def check_fcs(packet):
    packet = await alist(packet)
    fcs = zlib.crc32(bytes(packet))
    if fcs != FCS_GOOD:
        raise FrameCheckError
    elif len(packet) < 64:
        raise PaddingError
    return packet[:-4]

def recv_packet(mac):
    return check_fcs(skip_preamble(nibbles_to_bytes(mii_recv_packet(mac, {
        'ce': mac.mii_tx_ce,
        'data': mac.mii_txd,
        'valid': mac.mii_tx_en,
    }))))

async def expect_bad_fcs(mac):
    try:
        await recv_packet(mac)
    except FrameCheckError:
        pass
    else:
        raise AssertionError

class Status(enum.Enum):
    OK = enum.auto()
    GAVE_UP = enum.auto()
    LATE_COLLISION = enum.auto()
    UNDERFLOW = enum.auto()

async def get_status(mac):
    ok = 0
    gave_up = 0
    late = 0
    underflow = 0

    while not (ok or gave_up or late or underflow) or mac.mii_tx_en.value:
        ok += mac.transmit_ok.value
        gave_up += mac.gave_up.value
        late += mac.late_collision.value
        underflow += mac.underflow.value
        await FallingEdge(mac.clk)

    assert ok + gave_up + late + underflow == 1
    if ok:
        return Status.OK
    elif gave_up:
        return Status.GAVE_UP
    elif late:
        return Status.LATE_COLLISION
    elif underflow:
        return Status.UNDERFLOW

async def start(mac, packet, **kwargs):
    send = await cocotb.start(send_packet(mac, packet, **kwargs))
    status = await cocotb.start(get_status(mac))
    return send, status

BIT_TIME_NS = 10
BYTE_TIME_NS = 8 * BIT_TIME_NS

async def collide(mac, ns, duration=16):
    while not mac.mii_tx_en.value:
        await FallingEdge(mac.clk)

    if ns > 4:
        await Timer(ns - 4, 'ns')
    mac.mii_col.value = 1
    await Timer(duration, 'ns')
    mac.mii_col.value = 0

def randtime(min_bytes, max_bytes):
    return random.randrange(min_bytes * BYTE_TIME_NS, max_bytes * BYTE_TIME_NS)

async def restart(mac, ns):
    await cocotb.start(collide(mac, ns))
    await expect_bad_fcs(mac)

def compare(actual, expected):
    if actual[:len(expected)] != expected:
        print(actual)
        print(expected)
        raise AssertionError

async def ok(mac, packet, status, ns=None):
    if ns is not None:
        await cocotb.start(collide(mac, ns))
    compare(await recv_packet(mac), packet)
    assert await status.join() == Status.OK

@timeout(50, 'us')
async def test_send(mac, ratio):
    await init(mac)

    packets = (
        list(range(32)),
        list(range(56)),
        list(range(256)),
    )

    async def send_packets():
        for packet in packets:
            await send_packet(mac, packet, ratio=ratio)

    await cocotb.start(send_packets())
    for i, packet in enumerate(packets):
        status = await cocotb.start(get_status(mac))
        recv = await cocotb.start(recv_packet(mac))

        # Measure the IPG to ensure throughput
        start = get_sim_time('ns')
        while not mac.mii_tx_en.value:
            await RisingEdge(mac.clk)
        # The first IPG may not be exact
        if i:
            assert get_sim_time('ns') - start == 12 * 80 - 4

        compare(await recv.join(), packet)
        assert await status.join() == Status.OK

send_tests = TestFactory(test_send)
send_tests.add_option('ratio', (1, BIT_TIME_NS))
send_tests.generate_tests()

@cocotb.test(timeout_time=100, timeout_unit='us')
async def test_underflow(mac):
    await init(mac)

    async def underflow(mac, send, status):
        await expect_bad_fcs(mac)
        await send.join()
        assert await status.join() == Status.UNDERFLOW

    send, status = await start(mac, range(32), ratio=30)
    await underflow(mac, send, status)

    send, status = await start(mac, [*range(56), None])
    await underflow(mac, send, status)
    send, status = await start(mac, [*range(58), None])
    await underflow(mac, send, status)
    send, status = await start(mac, [*range(60), None])
    await underflow(mac, send, status)

    send, status = await start(mac, [*range(56), None, 1])
    await underflow(mac, send, status)
    send, status = await start(mac, [*range(58), None, 1])
    await underflow(mac, send, status)
    send, status = await start(mac, [*range(60), None, 1])
    await underflow(mac, send, status)

    send, status = await start(mac, [*range(56), None])
    await restart(mac, (8 + 55) * BYTE_TIME_NS)
    await underflow(mac, send, status)
    send, status = await start(mac, [*range(58), None])
    await restart(mac, (8 + 57) * BYTE_TIME_NS)
    await send.join()
    assert await status.join() == Status.LATE_COLLISION
    send, status = await start(mac, [*range(60), None])
    await restart(mac, (8 + 59) * BYTE_TIME_NS)
    await send.join()
    assert await status.join() == Status.LATE_COLLISION

@cocotb.test(timeout_time=1250, timeout_unit='us', skip=skip_slow)
async def test_backoff(mac):
    await init(mac)

    packet = list(range(32))
    for collisions in (15, 16):
        send, status = await start(mac, packet)
        then = None
        for n in range(collisions):
            await restart(mac, 0)
            now = get_sim_time('ns')
            if then is not None:
                assert now - then <= (8 + 4 + 12 + 2 ** min(n, 10)) * BYTE_TIME_NS
            then = now

        if collisions == 16:
            assert await status.join() == Status.GAVE_UP
        else:
            await ok(mac, packet, status)

@cocotb.test(timeout_time=10, timeout_unit='us')
async def test_defer(mac):
    await init(mac)

    # Skip to the end of IPG_LATE
    mac.mii_crs.value = 1
    await Timer(13 * BYTE_TIME_NS, 'ns')
    packet = list(range(32))
    send, status = await start(mac, packet)
    # Ensure IPG_EARLY works
    await Timer(13 * BYTE_TIME_NS, 'ns')
    assert not mac.mii_tx_en.value

    # Test the early 2/3s; not exact since the last 1/3 takes the slack
    mac.mii_crs.value = 0
    await Timer(7 * BYTE_TIME_NS, 'ns')
    mac.mii_crs.value = 1
    await Timer(6 * BYTE_TIME_NS, 'ns')
    assert not mac.mii_tx_en.value

    # And the late
    mac.mii_crs.value = 0
    await Timer(8 * BYTE_TIME_NS, 'ns')
    mac.mii_crs.value = 1
    await Timer(5 * BYTE_TIME_NS, 'ns')
    assert mac.mii_tx_en.value
    assert await status.join() == Status.OK

@cocotb.test(timeout_time=150, timeout_unit='us')
async def test_collision(mac):
    await init(mac)

    async def late(mac, packet, ns):
        send, status = await start(mac, packet)
        await restart(mac, ns)
        await send.join()
        assert await status.join() == Status.LATE_COLLISION

    packet = list(range(32))
    send, status = await start(mac, packet)
    await restart(mac, randtime(0, 8))
    await restart(mac, randtime(8, 40))
    await restart(mac, randtime(40, 64))
    await restart(mac, 64 * BYTE_TIME_NS - 1)
    await ok(mac, packet, status, 72 * BYTE_TIME_NS)

    await late(mac, packet, 64 * BYTE_TIME_NS)
    await late(mac, packet, randtime(64, 72))
    await late(mac, packet, (8 + 64) * BYTE_TIME_NS - 1)

    packet = list(range(256))
    send, status = await start(mac, packet)
    await restart(mac, randtime(8, 40))
    await restart(mac, randtime(40, 64))
    await restart(mac, 64 * BYTE_TIME_NS - 1)
    await ok(mac, packet, status, (8 + 256 + 4) * BYTE_TIME_NS)

    await late(mac, packet, 64 * BYTE_TIME_NS)
    await late(mac, packet, randtime(64, 256))
    await late(mac, packet, 72 * BYTE_TIME_NS - 1)
