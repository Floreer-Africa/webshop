"""Server-side contract for the checkout address form.

PR-Foundry fork addition (checkout address form design, 2026-09-24).

Registered through ``override_whitelisted_methods`` rather than by editing
``shopping_cart/cart.py``. webshop is an upstream fork here, so every line changed in a file
upstream owns is a line a sync can reset and a re-verify grep has to watch. The override
mechanism is the same one ``courier_guy_za`` uses to withdraw its shipping rule, and it keeps
the patch surface in upstream-owned files at zero.

Deliberately a top-level module and not ``webshop/webshop/api/…``: upstream ships
``webshop/webshop/api.py``, and a package beside it hides the module (see ``maps.py``).
"""

import re

import frappe
from frappe import _

# E.164: a leading +, a non-zero country digit, and at most 15 digits in total.
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def _validate_phone(doc: dict) -> None:
	"""Refuse anything that is not E.164, before the address is written.

	The form supplies E.164 from intl-tel-input, but that is a convenience and not a
	boundary: this endpoint is whitelisted and directly callable, so the server is what
	actually decides the stored shape.

	The number is required because it *is* the delivery contact number -- the courier
	notifies on it, and for a locker it carries the collection PIN. An address saved
	without one is an order nobody can be told about.
	"""
	phone = (doc.get("phone") or "").strip()
	if not phone:
		frappe.throw(
			_("A mobile number is required so the courier can contact you about delivery."),
			frappe.ValidationError,
		)
	if not _E164.match(phone):
		frappe.throw(
			_(
				"Enter the phone number in international format, starting with the country "
				"code — for example +27 82 123 4567."
			),
			frappe.ValidationError,
		)
	doc["phone"] = phone


@frappe.whitelist()
def add_new_address(doc):
	"""webshop's ``add_new_address``, with the phone validated first.

	Validation happens **before** delegating, so a refused number leaves nothing behind for
	the customer to trip over on their next visit.
	"""
	from webshop.webshop.shopping_cart.cart import add_new_address as _native

	doc = frappe.parse_json(doc)
	_validate_phone(doc)
	return _native(doc)
