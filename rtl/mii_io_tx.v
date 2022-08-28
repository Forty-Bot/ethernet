// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

`include "common.vh"
`include "io.vh"

module mii_io_tx (
	/* On-chip */
	input clk,
	output reg ce,
	output reg enable,
	output reg err,
	output reg [3:0] data,

	/* Off-chip */
	output reg tx_clk,
	input tx_en,
	input tx_er,
	input [3:0] txd
);

	reg ce_next;
	reg tx_clk_p_next, tx_clk_n, tx_clk_n_next;
	reg [2:0] counter, counter_next;
	/* I have no idea why we need to use initial... */
	initial counter = 4;

	always @(*) begin
		tx_clk_p_next = 0;
		tx_clk_n_next = 0;
		ce_next = 0;
		counter_next = counter - 1;
		case (counter)
		4, 3: begin
			tx_clk_p_next = 1;
			tx_clk_n_next = 1;
		end
		2: tx_clk_p_next = 1;
		1: ;
		0: begin
			ce_next = 1;
			counter_next = 4;
		end
		endcase
	end

	always @(posedge clk) begin
		counter <= counter_next;
		tx_clk_n <= tx_clk_n_next;
		ce <= ce_next;
	end

`ifdef SYNTHESIS
	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_ALWAYS | `PIN_OUTPUT_DDR)
	) tx_clk_pin (
		.PACKAGE_PIN(tx_clk),
		.OUTPUT_CLK(clk),
		.D_OUT_0(tx_clk_p_next),
		.D_OUT_1(tx_clk_n)
	);

	SB_IO #(
		.PIN_TYPE(`PIN_INPUT_REGISTERED)
	) tx_en_pin (
		.PACKAGE_PIN(tx_en),
		.CLOCK_ENABLE(ce_next),
		.INPUT_CLK(clk),
		.D_IN_0(enable)
	);

	SB_IO #(
		.PIN_TYPE(`PIN_INPUT_REGISTERED)
	) tx_er_pin (
		.PACKAGE_PIN(tx_er),
		.CLOCK_ENABLE(ce_next),
		.INPUT_CLK(clk),
		.D_IN_0(err)
	);

	genvar i;
	generate for (i = 0; i < 4; i = i + 1) begin
		SB_IO #(
			.PIN_TYPE(`PIN_INPUT_REGISTERED)
		) txd_pin (
			.PACKAGE_PIN(txd[i]),
			.CLOCK_ENABLE(ce_next),
			.INPUT_CLK(clk),
			.D_IN_0(data[i])
		);
	end
	endgenerate
`else
	always @(posedge clk) begin
		tx_clk <= tx_clk_p_next;
		if (ce_next) begin
			enable <= tx_en;
			err <= tx_er;
			data <= txd;
		end
	end

	always @(negedge clk)
		tx_clk <= tx_clk_n;
`endif

	`DUMP(0)

endmodule
