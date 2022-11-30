# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

Q = 1
SYNTH = yosys
PNR = nextpnr-ice40
ICARUS = iverilog
VVP = vvp

.DELETE_ON_ERROR:

.PHONY: all
all: rtl/pcs.asc

.PHONY: FORCE
FORCE:

log:
	mkdir $@

%.synth.json: %.v | log
	$(SYNTH) -q -E $@.d -p "synth_ice40 -top $(*F)" -b json -o $@ -f verilog $< -l log/$(*F).synth

define run-jsontov =
	( grep timescale $*.v; $(SYNTH) -q -p "write_verilog -defparam -noattr" -f json $< ) > $@
endef

%.synth.v: %.synth.json %.v
	$(run-jsontov)

%.place.v: %.place.json %.v
	$(run-jsontov)

# Don't warn about including the timescale from common.vh
IFLAGS := -g2012 -gspecify -Wall -Wno-timescale
EXTRA_V := rtl/iverilog_dump.v

define run-icarus =
$(ICARUS) $(IFLAGS) -I$(<D) -y$(<D) -M$@.pre -DTOP=$(TOP) -s $(TOP) -s iverilog_dump -o $@ $< $(EXTRA_V) && \
	( echo -n "$@: " && tr '\n' ' ' ) < $@.pre > $@.d; RET=$$?; rm -f $@.pre; exit $$RET
endef

%.vvp: TOP = $(*F)
%.vvp: %.v rtl/iverilog_dump.v
	$(run-icarus)

%.synth.vvp: TOP = $(*F)
%.synth.vvp %.place.vvp: EXTRA_V += $(shell $(SYNTH)-config --datdir)/ice40/cells_sim.v
# Don't warn about unused SB_IO ports
%.synth.vvp: IFLAGS += -Wno-portbind
%.synth.vvp: %.synth.v rtl/iverilog_dump.v
	$(run-icarus)

%.place.vvp: TOP = top
# Don't warn about unused SB_IO ports
%.place.vvp: IFLAGS += -Wno-portbind
%.place.vvp: IFLAGS += -DTIMING -Ttyp
%.place.vvp: %.place.v rtl/iverilog_dump.v
	$(run-icarus)

%.asc %.sdf %.place.json &: %.synth.json | log
	$(PNR) -q --pcf-allow-unconstrained --freq 125 --hx8k --package ct256 --json $< \
		--write $*.place.json --sdf $*.sdf --asc $*.asc --log log/$(*F).place

-include $(wildcard rtl/*.d)

export LIBPYTHON_LOC := $(shell cocotb-config --libpython)
VVPFLAGS := -M $(shell cocotb-config --lib-dir)
VVPFLAGS += -m $(shell cocotb-config --lib-name vpi icarus)
PLUSARGS = -fst +vcd=$@

# Always use color output if we have a tty. This allows for easy use of -O
ifeq ($(shell test -c /dev/stdin && echo 1),1)
export COCOTB_ANSI_OUTPUT=1
endif

define run-vvp =
MODULE=tb.$* $(VVP) $(VVPFLAGS) $< $(PLUSARGS)
endef

%.fst: PLUSARGS += +levels=0
%.fst: rtl/%.vvp tb/%.py FORCE
	$(run-vvp)

%.synth.fst: PLUSARGS += +levels=1
%.synth.fst: rtl/%.synth.vvp tb/%.py FORCE
	$(run-vvp)

%.place.fst: PLUSARGS += +levels=1 +sdf=rtl/$*.sdf
%.place.fst: rtl/%.place.vvp rtl/%.sdf tb/%.py FORCE
	$(run-vvp)

MODULES := pcs_rx pcs_tx pmd_dp83223_rx nrzi_encode nrzi_decode scramble descramble mdio mdio_io
MODULES += mii_io_rx mii_io_tx mdio_regs phy_core axis_replay_buffer

.PHONY: test
test: $(addsuffix .fst,$(MODULES)) $(addsuffix .synth.fst,$(MODULES))
#test: $(addsuffix .place.fst,$(MODULES))

.PHONY: asc
asc: $(addprefix rtl/,$(addsuffix .asc,$(MODULES)))

.PHONY: clean
clean:
	rm -f *.fst
	rm -rf log
	cd rtl && rm -f *.json *.asc *.pre *.vvp *.d *.synth.v *.place.v
