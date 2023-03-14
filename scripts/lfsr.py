#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import functools
import sys

def logbits(x):
    b = 0
    while x:
        if x & 1:
            yield b
        b += 1
        x >>= 1

@functools.cache
def logstep_bit(taps, bit, logsteps):
    if not logsteps:
        return (bit < taps[0]) << (bit + 1) | (bit in taps)
    return logstep_state(taps, logstep_bit(taps, bit, logsteps - 1), logsteps - 1)

def logstep_state(taps, state, logsteps):
    lfsr = 0
    for bit in logbits(state):
        lfsr ^= logstep_bit(taps, bit, logsteps)
    return lfsr

def step_state(taps, state, steps):
    for logsteps in logbits(steps):
        state = logstep_state(taps, state, logsteps)
    return state

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"""Usage: {sys.argv[0]} TAPS CYCLES...
Calculate the starting state to use with the LFSR defined by TAPS (as an
integer) which will go through CYCLES states before finishing.""", file=sys.stderr)
        sys.exit(1)

    taps = tuple(reversed(tuple(logbits(int(sys.argv[1], base=0)))))
    max_cycles = (1 << taps[0] + 1) - 1
    for cycles in sys.argv[2:]:
        cycles = int(cycles, base=0)
        if cycles > max_cycles:
            print(f"Maximum cycles is {max_cycles:#x}, got {cycles:#x}",
                  file=sys.stderr)
        elif cycles <= 0:
            print(f"Minimum cycles is 1, got {cycles}", file=sys.stderr)
        else:
            state = step_state(taps, max_cycles, max_cycles - cycles + 1)
            print(f"{taps[0] + 1}'h{state:0{(taps[0] + 4) // 4}x}")
