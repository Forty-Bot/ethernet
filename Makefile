# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

Q = 1
SYNTH = yosys
PNR = nextpnr-ice40
ICARUS = iverilog
VVP = vvp

.DELETE_ON_ERROR:

.PHONY: all
all: examples/breakout_hub/top.bin

.PHONY: FORCE
FORCE:

log:
	mkdir $@

INCDIRS := rtl
LIBDIRS := rtl lib/verilog-lfsr/rtl
%.synth.json: %.v | log
	$(SYNTH) -q -E $@.d -b json -o $@ -l log/$(*F).synth \
		-p "read_verilog $(addprefix -I ,$(INCDIRS)) -sv $<" \
		-p "hierarchy $(addprefix -libdir ,$(LIBDIRS) $(<D))" \
		-p "synth_ice40 -top $(*F)"

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
$(ICARUS) $(IFLAGS) -I$(<D) $(addprefix -y,$(LIBDIRS) $(<D)) -M$@.pre -DTOP=$(TOP) \
	-s $(TOP) -s iverilog_dump -o $@ $< $(EXTRA_V) && \
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

PNRARGS := --freq 125 --hx8k --package ct256 --pcf-allow-unconstrained --no-promote-globals

define run-pnr =
	$(PNR) -q $(PNRARGS) --json $< --log log/$(*F).$(LOG_EXT)
endef

%.sdf %.place.json &: PNRARGS += --write $*.place.json --sdf $*.sdf
%.sdf %.place.json &: LOG_EXT := place
%.sdf %.place.json &: %.synth.json | log
	$(run-pnr)

PNR_RETRIES := 10

%.asc: PNRARGS += --pcf $*.pcf --asc $@ -r
%.asc: LOG_EXT := asc
%.asc: %.synth.json %.pcf | log
	for i in $$(seq $(PNR_RETRIES)); do \
		if $(run-pnr); then \
			exit 0; \
		fi \
	done; \
	exit 1

%.bin: %.asc
	$(ICEPACK) $< $@

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

MODULES += axis_replay_buffer
MODULES += descramble
MODULES += hub
MODULES += led_blinker
MODULES += mdio
MODULES += mdio_io
MODULES += mdio_regs
MODULES += mii_elastic_buffer
MODULES += mii_io_rx
MODULES += mii_io_tx
MODULES += nrzi_decode
MODULES += nrzi_encode
MODULES += pcs_rx
MODULES += pcs_tx
MODULES += phy_core
MODULES += pmd_dp83223
MODULES += pmd_dp83223_rx
MODULES += scramble
MODULES += wb_mux

.PHONY: test
test: $(addsuffix .fst,$(MODULES)) $(addsuffix .synth.fst,$(MODULES))
#test: $(addsuffix .place.fst,$(MODULES))

.PHONY: asc
asc: $(addprefix rtl/,$(addsuffix .asc,$(MODULES)))

CLEAN_EXT := .json .asc .pre .vvp .d .synth.v .place.v .sdf .bin

.PHONY: clean
clean:
	rm -f *.fst
	rm -rf log
	rm -f $(addprefix rtl/*,$(CLEAN_EXT))
	rm -f $(addprefix examples/*/*,$(CLEAN_EXT))
