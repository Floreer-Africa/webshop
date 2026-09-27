// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// JS exclusive to /cart page
frappe.provide("webshop.webshop.shopping_cart");
var shopping_cart = webshop.webshop.shopping_cart;

$.extend(shopping_cart, {
	show_error: function (title, text) {
		$("#cart-container").html(
			'<div class="msg-box"><h4>' +
				title +
				'</h4><p class="text-muted">' +
				text +
				"</p></div>"
		);
	},

	// framework#167 — render a server-side failure where the shopper can see it.
	// `_server_messages` is a JSON array of JSON *strings*, so each entry needs a
	// second parse to reach its human text (framework#143). Shared by the success
	// callback and the error handler so the two can never drift apart again.
	extract_server_messages: function(r) {
		if (!r || !r._server_messages) return "";
		var raw;
		try { raw = JSON.parse(r._server_messages) || []; } catch (e) { return ""; }
		if (!Array.isArray(raw)) return "";
		return raw.map(function(m) {
			try { return JSON.parse(m).message || m; } catch (e) { return m; }
		}).join("<br>");
	},

	show_cart_error: function(r) {
		shopping_cart.unfreeze();
		$("#cart-error")
			.empty()
			.html(shopping_cart.extract_server_messages(r) || frappe._("Something went wrong!"))
			.toggle(true);
	},

	bind_events: function () {
		shopping_cart.bind_place_order();
		shopping_cart.bind_request_quotation();
		shopping_cart.bind_change_qty();
		shopping_cart.bind_remove_cart_item();
		shopping_cart.bind_change_notes();
		shopping_cart.bind_coupon_code();
		shopping_cart.bind_remove_coupon_code();
	},

	bind_place_order: function () {
		$(".btn-place-order").on("click", function () {
			shopping_cart.place_order(this);
		});
	},

	bind_request_quotation: function () {
		$(".btn-request-for-quotation").on("click", function () {
			shopping_cart.request_quotation(this);
		});
	},

	bind_change_qty: function () {
		// bind update button
		$(".cart-items").on("change", ".cart-qty", function () {
			var item_code = $(this).attr("data-item-code");
			var newVal = $(this).val();
			shopping_cart.shopping_cart_update({ item_code, qty: newVal });
		});

		$(".cart-items").on("click", ".number-spinner button", function () {
			var btn = $(this),
				input = btn.closest(".number-spinner").find("input"),
				oldValue = input.val().trim(),
				newVal = 0;

			if (btn.attr("data-dir") == "up") {
				newVal = parseInt(oldValue) + 1;
			} else {
				if (oldValue > 1) {
					newVal = parseInt(oldValue) - 1;
				}
			}
			input.val(newVal);

			let notes = input.closest("td").siblings().find(".notes").text().trim();
			var item_code = input.attr("data-item-code");
			shopping_cart.shopping_cart_update({
				item_code,
				qty: newVal,
				additional_notes: notes,
			});
		});
	},

	bind_change_notes: function () {
		$(".cart-items").on("change", "textarea", function () {
			const $textarea = $(this);
			const item_code = $textarea.attr("data-item-code");
			const qty = $textarea.closest("tr").find(".cart-qty").val();
			const notes = $textarea.val();
			shopping_cart.shopping_cart_update({
				item_code,
				qty,
				additional_notes: notes,
			});
		});
	},

	bind_remove_cart_item: function () {
		$(".cart-items").on("click", ".remove-cart-item", (e) => {
			const $remove_cart_item_btn = $(e.currentTarget);
			var item_code = $remove_cart_item_btn.data("item-code");

			shopping_cart.shopping_cart_update({
				item_code: item_code,
				qty: 0,
			});
		});
	},

	render_tax_row: function ($cart_taxes, doc, shipping_rules) {
		var shipping_selector;
		if (shipping_rules) {
			shipping_selector =
				'<select class="form-control">' +
				$.map(shipping_rules, function (rule) {
					return '<option value="' + rule[0] + '">' + rule[1] + "</option>";
				}).join("\n") +
				"</select>";
		}

		var $tax_row = $(
			repl(
				'<div class="row">\
			<div class="col-md-9 col-sm-9">\
				<div class="row">\
					<div class="col-md-9 col-md-offset-3">' +
					(shipping_selector || "<p>%(description)s</p>") +
					'</div>\
				</div>\
			</div>\
			<div class="col-md-3 col-sm-3 text-right">\
				<p' +
					(shipping_selector ? ' style="margin-top: 5px;"' : "") +
					">%(formatted_tax_amount)s</p>\
			</div>\
		</div>",
				doc
			)
		).appendTo($cart_taxes);

		if (shipping_selector) {
			$tax_row.find("select option").each(function (i, opt) {
				if ($(opt).html() == doc.description) {
					$(opt).attr("selected", "selected");
				}
			});
			$tax_row.find("select").on("change", function () {
				shopping_cart.apply_shipping_rule($(this).val(), this);
			});
		}
	},

	apply_shipping_rule: function (rule, btn) {
		return frappe.call({
			btn: btn,
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.apply_shipping_rule",
			args: { shipping_rule: rule },
			callback: function (r) {
				if (!r.exc) {
					shopping_cart.render(r.message);
				}
			},
		});
	},

	place_order: function (btn) {
		shopping_cart.freeze();

		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.place_order",
			btn: btn,
			callback: function(r) {
				if(r.exc) {
					shopping_cart.show_cart_error(r);
				} else {
					$(btn).hide();
					window.location.href = '/orders/' + encodeURIComponent(r.message);
				}			},
			// framework#167 — a frappe.throw comes back as HTTP 417, and frappe's
			// 417 handler calls error_callback ONLY: never `callback`, and (unlike
			// its 413 sibling) it does not msgprint either. With no `error` handler
			// the incomplete-delivery-address throw showed the shopper NOTHING and
			// left the page frozen, while writing no Error Log row server-side.
			error: function(r) {
				shopping_cart.show_cart_error(r);
			}
		});
	},

	request_quotation: function (btn) {
		shopping_cart.freeze();

		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.request_for_quotation",
			btn: btn,
			callback: function(r) {
				if(r.exc) {
					shopping_cart.show_cart_error(r);
				} else {
					$(btn).hide();
					window.location.href = '/quotations/' + encodeURIComponent(r.message);
				}			},
			// framework#167 — a frappe.throw comes back as HTTP 417, and frappe's
			// 417 handler calls error_callback ONLY: never `callback`, and (unlike
			// its 413 sibling) it does not msgprint either. With no `error` handler
			// the incomplete-delivery-address throw showed the shopper NOTHING and
			// left the page frozen, while writing no Error Log row server-side.
			error: function(r) {
				shopping_cart.show_cart_error(r);
			}
		});
	},

	bind_coupon_code: function () {
		$(".bt-coupon").on("click", function () {
			shopping_cart.apply_coupon_code(this);
		});
	},

	apply_coupon_code: function (btn) {
		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.apply_coupon_code",
			btn: btn,
			args: {
				applied_code: $(".txtcoupon").val(),
				applied_referral_sales_partner: $(".txtreferral_sales_partner").val(),
			},
			callback: function (r) {
				if (r && r.message) {
					location.reload();
				}
			},
		});
	},

	bind_remove_coupon_code: function () {
		$(".bt-remove-coupon-code").on("click", function () {
			shopping_cart.remove_coupon_code(this);
		});
	},
	remove_coupon_code: function (btn) {
		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.remove_coupon_code",
			btn: btn,
			callback: function (r) {
				if (r && r.message) {
					location.reload();
				}
			},
		});
	},
});

frappe.ready(function () {
	if (window.location.pathname === "/cart") {
		$(".cart-icon").hide();
	}
	shopping_cart.parent = $(".cart-container");
	shopping_cart.bind_events();
});

function show_terms() {
	var html = $(".cart-terms").html();
	frappe.msgprint(html);
}
