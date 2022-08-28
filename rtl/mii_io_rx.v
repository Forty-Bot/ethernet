// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

`include "common.vh"
`include "io.vh"

module mii_io_rx (
	/* On-chip */
	input clk,
	input ce,
	input valid,
	input err,
	input [3:0] data,

	/* Off-chip */
	output reg rx_clk,
	output reg rx_dv,
	output reg rx_er,
	output reg [3:0] rxd
);

	reg rx_clk_p_next, rx_clk_n, rx_clk_n_next;
	reg [1:0] state = HIGH, state_next;

	parameter LOW		= 2;
	parameter RISING	= 1;
	parameter HIGH		= 0;

	always @(*) begin
		rx_clk_p_next = 0;
		rx_clk_n_next = 0;
		if (ce) begin
			state_next = LOW;
		end else case (state)
		LOW: begin
			state_next = RISING;
		end
		RISING: begin
			state_next = HIGH;
			rx_clk_n_next = 1;
		end
		HIGH: begin
			state_next = HIGH;
			rx_clk_p_next = 1;
			rx_clk_n_next = 1;
		end
		endcase
	end

	always @(posedge clk) begin
		state <= state_next;
		rx_clk_n <= rx_clk_n_next;
	end

`ifdef SYNTHESIS
	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_ALWAYS | `PIN_OUTPUT_DDR)
	) rx_clk_pin (
		.PACKAGE_PIN(rx_clk),
		.OUTPUT_CLK(clk),
		.D_OUT_0(rx_clk_p_next),
		.D_OUT_1(rx_clk_n)
	);

	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_ALWAYS | `PIN_OUTPUT_REGISTERED)
	) rx_dv_pin (
		.PACKAGE_PIN(rx_dv),
		.CLOCK_ENABLE(ce),
		.OUTPUT_CLK(clk),
		.D_OUT_0(valid)
	);

	SB_IO #(
		.PIN_TYPE(`PIN_OUTPUT_ALWAYS | `PIN_OUTPUT_REGISTERED)
	) rx_er_pin (
		.PACKAGE_PIN(rx_er),
		.CLOCK_ENABLE(ce),
		.OUTPUT_CLK(clk),
		.D_OUT_0(err)
	);

	genvar i;
	generate for (i = 0; i < 4; i = i + 1) begin
		SB_IO #(
			.PIN_TYPE(`PIN_OUTPUT_ALWAYS | `PIN_OUTPUT_REGISTERED)
		) rxd_pin (
			.PACKAGE_PIN(rxd[i]),
			.CLOCK_ENABLE(ce),
			.OUTPUT_CLK(clk),
			.D_OUT_0(data[i])
		);
	end
	endgenerate
`else
	always @(posedge clk) begin
		rx_clk <= rx_clk_p_next;
		if (ce) begin
			rx_dv <= valid;
			rx_er <= err;
			rxd <= data;
		end
	end

	always @(negedge clk)
		rx_clk <= rx_clk_n;
`endif

	`DUMP(0)

endmodule
