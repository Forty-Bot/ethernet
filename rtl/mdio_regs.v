// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

`include "common.vh"

module mdio_regs (
	/* Wishbone */
	input clk,
	output reg ack, err,
	input cyc, stb, we,
	input [4:0] addr,
	input [15:0] data_write,
	output reg [15:0] data_read,

	/* Control signals */
	input link_status,
	output reg loopback,
	output reg pdown,
	output reg isolate,
	output reg coltest
);

	/* The current price of a CID is $805... */
	parameter [23:0] OUI		= 0;
	parameter [5:0] MODEL		= 0;
	parameter [3:0] REVISION	= 0;
	/*
	 * Normally, this module will assert err when read/writing to an
	 * unknown register. The master will detect this and won't drive MDIO
	 * line. However, this might be undesirable if there is no external
	 * MDIO bus. Setting this parameter to 0 will cause it to ack all
	 * transactions. Writes to unknown registers will be ignored, and
	 * reads from unknown registers will yield 16'hffff, emulating
	 * a pull-up on MDIO.
	 */
	parameter EMULATE_PULLUP	= 0;

	localparam BMCR		= 0;
	localparam BMSR		= 1;
	localparam ID1		= 2;
	localparam ID2		= 3;

	localparam BMCR_RESET		= 15;
	localparam BMCR_LOOPBACK	= 14;
	localparam BMCR_SPEED_LSB	= 13;
	localparam BMCR_PDOWN		= 11;
	localparam BMCR_ISOLATE		= 10;
	localparam BMCR_DUPLEX		= 8;
	localparam BMCR_COLTEST		= 7;
	localparam BMCR_SPEED_MSB	= 6;

	localparam BMSR_100FULL		= 14;
	localparam BMSR_100HALF		= 13;
	localparam BMSR_LSTATUS		= 2;
	localparam BMSR_EXTCAP		= 0;

	integer i;
	reg duplex, link_status_latched;
	reg loopback_next, pdown_next, isolate_next, duplex_next, coltest_next;
	reg link_status_latched_next;
	reg [15:0] data_read_next;

	initial begin
		loopback = 0;
		pdown = 0;
		isolate = 1;
		duplex = 0;
		coltest = 0;
		link_status_latched = 0;
	end

	always @(*) begin
		loopback_next = loopback;
		pdown_next = pdown;
		isolate_next = isolate;
		duplex_next = duplex;
		coltest_next = coltest;
		link_status_latched_next = link_status_latched && link_status;

		data_read_next = 0;
		ack = cyc && stb;
		err = 0;
		case (addr)
		BMCR: begin
			data_read_next[BMCR_LOOPBACK] = loopback;
			data_read_next[BMCR_SPEED_LSB] = 1; /* 100 Mb/s */
			data_read_next[BMCR_PDOWN] = pdown;
			data_read_next[BMCR_ISOLATE] = isolate;
			data_read_next[BMCR_DUPLEX] = duplex;
			data_read_next[BMCR_COLTEST] = coltest;

			if (cyc && stb && we) begin
				loopback_next = data_write[BMCR_LOOPBACK];
				pdown_next = data_write[BMCR_PDOWN];
				isolate_next = data_write[BMCR_ISOLATE];
				duplex_next = data_write[BMCR_DUPLEX];
				coltest_next = data_write[BMCR_COLTEST];

				if (data_write[BMCR_RESET]) begin
					loopback_next = 0;
					pdown_next = 0;
					isolate_next = 1;
					duplex_next = 0;
					coltest_next = 0;
					link_status_latched_next = link_status;
				end
			end
		end
		BMSR: begin
			data_read_next[BMSR_100FULL] = 1;
			data_read_next[BMSR_100HALF] = 1;
			data_read_next[BMSR_LSTATUS] = link_status_latched;
			data_read_next[BMSR_EXTCAP] = 1;

			if (cyc && stb && !we)
				link_status_latched_next = link_status;
		end
		ID1: begin
			for (i = 0; i < 16; i = i + 1)
				data_read_next[i] = OUI[17 - i];
		end
		ID2: begin
			data_read_next[3:0] = REVISION;
			data_read_next[9:4] = MODEL;
			for (i = 0; i < 6; i = i + 1)
				data_read_next[i + 4] = OUI[23 - i];
		end
		default: begin
			if (EMULATE_PULLUP) begin
				data_read_next = 16'hFFFF;
			end else begin
				ack = 0;
				err = stb && cyc;
				data_read_next = 16'hXXXX;
			end
		end
		endcase
	end

	always @(posedge clk) begin
		loopback <= loopback_next;
		pdown <= pdown_next;
		isolate <= isolate_next;
		duplex <= duplex_next;
		coltest <= coltest_next;
		link_status_latched <= link_status_latched_next;
		data_read <= data_read_next;
	end

	`DUMP(0)

endmodule
