"""Per-IP throttles on the guest cart's coupon endpoints (framework#284).

PR-Foundry fork addition, registered through ``override_whitelisted_methods`` like
``item_inquiry.py``, so no upstream-owned file changes.

``apply_coupon_code`` and ``remove_coupon_code`` are ``allow_guest`` and write the cart
Quotation. ``apply_coupon_code`` answers whether a guessed code is valid, so without a
throttle an anonymous client could enumerate coupon codes as fast as it can send requests.
A shopper applies or removes a coupon a handful of times at most.
"""

import frappe
from frappe.rate_limiter import rate_limit

COUPON_RATE = {"limit": 10, "seconds": 60}


@frappe.whitelist(allow_guest=True)
@rate_limit(**COUPON_RATE)
def apply_coupon_code(applied_code, applied_referral_sales_partner):
	from webshop.webshop.shopping_cart.cart import apply_coupon_code as native

	return native(applied_code, applied_referral_sales_partner)


@frappe.whitelist(allow_guest=True)
@rate_limit(**COUPON_RATE)
def remove_coupon_code():
	from webshop.webshop.shopping_cart.cart import remove_coupon_code as native

	return native()
