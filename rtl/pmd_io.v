// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 *
 * This roughly follows the design of XAPP225. However, we use a 2x rate DDR
 * clock instead of two clocks 90 degrees out of phase. Yosys/nextpnr cannot
 * guarantee the phase relationship of any clocks, even those from the same
 * PLL. Because of this, we assume that rx_clk_250 and rx_clk_125 are unrelated.
 */

`include "common.vh"
`include "io.vh"

`timescale 1ns/1ps

module pmd_io (
	input tx_clk,
	input rx_clk_250,
	input rx_clk_125,

	input signal_detect,
	output reg tx_p, tx_n,
	input rx,

	/* PMD */
	output signal_status,
	input pmd_data_tx,
	output reg [1:0] pmd_data_rx,
	output reg [1:0] pmd_data_rx_valid
);

	reg [1:0] rx_p, rx_n;
	reg [3:0] sd_delay;

`ifdef SYNTHESIS
	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_NEVER | `PIN_INPUT_REGISTERED),
		.IO_STANDARD("SB_LVDS_INPUT")
	) signal_detect_pin (
		.PACKAGE_PIN(signal_detect),
		.INPUT_CLK(rx_clk_125),
		.D_IN_0(sd_delay[0])
	);

	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_NEVER | `PIN_INPUT_DDR),
		.IO_STANDARD("SB_LVDS_INPUT")
	) data_rx_pin (
		.PACKAGE_PIN(rx),
		.INPUT_CLK(rx_clk_250),
		.D_IN_0(rx_p[0]),
		.D_IN_1(rx_n[0])
	);
`else
	always @(posedge rx_clk_125)
		sd_delay[0] <= signal_detect;

	always @(posedge rx_clk_250)
		rx_p[0] <= rx;

	always @(negedge rx_clk_250)
		rx_n[0] <= rx;
`endif

	/*
	 * Delay signal status until the known good data has had a chance to
	 * make it through the pipeline. This isn't necessary for real hardware
	 * (since signal status is asserted long after we have good data), but
	 * it helps out during simulation. It also helps avoid metastability.
	 */
	always @(posedge rx_clk_125)
		sd_delay[3:1] <= sd_delay[2:0];

	assign signal_status = sd_delay[3];

	/*
	 * Get things into the rx_clk_250 domain so that we sample posedge before
	 * negedge. Without this we can have a negedge which happens before the
	 * posedge.
	 */
	always @(posedge rx_clk_250) begin
		rx_p[1] <= rx_p[0];
		rx_n[1] <= rx_n[0];
	end

	reg [2:0] rx_a, rx_b, rx_c, rx_d;

	/* Get everything in the rx_clk_125 domain */
	always @(posedge rx_clk_125) begin
		rx_a[0] <= rx_p[1];
		rx_b[0] <= rx_n[1];
	end

	always @(negedge rx_clk_125) begin
		rx_c[0] <= rx_p[1];
		rx_d[0] <= rx_n[1];
	end

	/*
	 * Buffer things a bit. We wait a cycle to avoid metastability. After
	 * that, we need two cycles of history to detect edges.
	 */
	always @(posedge rx_clk_125) begin
		rx_a[2:1] <= rx_a[1:0];
		rx_b[2:1] <= rx_b[1:0];
		rx_c[2:1] <= rx_c[1:0];
		rx_d[2:1] <= rx_d[1:0];
	end

	localparam A = 0;
	localparam B = 1;
	localparam C = 2;
	localparam D = 3;

	reg [1:0] state = A, state_next;
	reg valid = 0, valid_next;
	reg [1:0] pmd_data_rx_next, pmd_data_rx_valid_next;
	reg [3:0] rx_r, rx_f;

	always @(*) begin
		rx_r = { 
			rx_a[1] & ~rx_a[2],
			rx_b[1] & ~rx_b[2],
			rx_c[1] & ~rx_c[2],
			rx_d[1] & ~rx_d[2]
		};

		rx_f = {
			~rx_a[1] & rx_a[2],
			~rx_b[1] & rx_b[2],
			~rx_c[1] & rx_c[2],
			~rx_d[1] & rx_d[2]
		};

		state_next = state;
		valid_next = 1;
		if (rx_r == 4'b1111 || rx_f == 4'b1111)
			state_next = C;
		else if (rx_r == 4'b1000 || rx_f == 4'b1000)
			state_next = D;
		else if (rx_r == 4'b1100 || rx_f == 4'b1100)
			state_next = A;
		else if (rx_r == 4'b1110 || rx_f == 4'b1110)
			state_next = B;
		else
			valid_next = valid;

		if (!signal_status) begin
			state_next = A;
			valid_next = 0;
		end
		
		pmd_data_rx_next[0] = rx_d[2];
		pmd_data_rx_valid_next = 1;
		case (state_next)
		A: begin
			pmd_data_rx_next[1] = rx_a[2];
			if (state == D)
				pmd_data_rx_valid_next = 0;
		end
		B: begin
			pmd_data_rx_next[1] = rx_b[2];
		end
		C: begin
			pmd_data_rx_next[1] = rx_c[2];
		end
		D: begin
			pmd_data_rx_next[1] = rx_d[2];
			if (state == A) begin
				pmd_data_rx_next[1] = rx_a[2];
				pmd_data_rx_valid_next = 2;
			end
		end
		endcase

		if (!valid_next)
			pmd_data_rx_valid_next = 0;
	end

	always @(posedge rx_clk_125) begin
		state <= state_next;
		valid <= valid_next;
		pmd_data_rx <= pmd_data_rx_next;
		pmd_data_rx_valid <= pmd_data_rx_valid_next;
	end

`ifdef SYNTHESIS
	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_ALWAYS | `PIN_OUTPUT_REGISTERED),
		.IO_STANDARD("SB_LVDS_INPUT")
	) data_txp_pin (
		.PACKAGE_PIN(tx_p),
		.OUTPUT_CLK(rx_clk_125),
		.D_OUT_0(pmd_data_tx)
	);

	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_ALWAYS | `PIN_OUTPUT_REGISTERED_INVERTED),
		.IO_STANDARD("SB_LVDS_INPUT")
	) data_txn_pin (
		.PACKAGE_PIN(tx_n),
		.OUTPUT_CLK(rx_clk_125),
		.D_OUT_0(pmd_data_tx)
	);
`else
	always @(posedge tx_clk) begin
		tx_p <= pmd_data_tx;
		tx_n <= ~pmd_data_tx;
	end
`endif

`ifndef SYNTHESIS
	reg [255:0] state_text;
	input [13:0] delay;

	always @(*) begin
		case (state)
		A: state_text = "A";
		B: state_text = "B";
		C: state_text = "C";
		D: state_text = "D";
		endcase
	end
`endif

	`DUMP(0)

endmodule
