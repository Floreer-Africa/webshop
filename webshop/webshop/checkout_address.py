"""Server-side contract for the checkout address form.

PR-Foundry fork addition (checkout address form design, 2026-09-24).

Registered through ``override_whitelisted_methods`` rather than by editing
``shopping_cart/cart.py``. webshop is an upstream fork here, so every line changed in a file
upstream owns is a line a sync can reset and a re-verify grep has to watch. The override
mechanism is the same one ``za_courier_guy`` uses to withdraw its shipping rule, and it keeps
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


# What the checkout form shows, and so everything an edit may touch. ``links`` is absent on
# purpose: who an address belongs to is not something the customer edits from the cart.
EDITABLE_FIELDS = (
	"address_title",
	"address_type",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"pincode",
	"country",
	"phone",
	"email_id",
	"custom_latitude",
	"custom_longitude",
	"custom_place_id",
)


def _owned_address(name):
	"""The session customer's own Address, or ``PermissionError``.

	"Own" means exactly what the cart means by it -- linked to the party ``get_party``
	resolves, the same link ``get_address_docs`` lists the cards from. A missing address
	raises the same error as someone else's, so this cannot be used to probe names.
	"""
	from webshop.webshop.shopping_cart.cart import get_party

	refused = frappe.PermissionError(_("You cannot edit this address."))
	if frappe.session.user == "Guest" or not name:
		raise refused
	party = get_party()
	if not party or not frappe.db.exists(
		"Dynamic Link",
		{
			"parenttype": "Address",
			"parent": name,
			"link_doctype": party.doctype,
			"link_name": party.name,
		},
	):
		raise refused
	return frappe.get_doc("Address", name)


def _editable_fields(address) -> tuple:
	# The coordinate fields are Custom Fields; a site without them must not fail the edit.
	return tuple(f for f in EDITABLE_FIELDS if address.meta.has_field(f))


@frappe.whitelist()
def get_address(name):
	"""Pre-fill values for editing ``name`` in the checkout form (framework#253)."""
	address = _owned_address(name)
	values = {f: address.get(f) for f in _editable_fields(address)}
	values["name"] = address.name
	return values


@frappe.whitelist()
def update_address(name, doc):
	"""Save an edit from the checkout form, with the same phone rule as ``add_new_address``.

	Replaces the cart's route into erpnext's stock ``addresses`` Web Form, which stored the
	phone as typed. Only ``EDITABLE_FIELDS`` are written; anything else in ``doc`` is
	ignored rather than refused, because the form never sends it.
	"""
	address = _owned_address(name)
	doc = frappe.parse_json(doc)
	_validate_phone(doc)
	for fieldname in _editable_fields(address):
		if fieldname in doc:
			address.set(fieldname, doc.get(fieldname))
	# Ownership was established above; the customer holds no desk write on Address, the
	# same reason the native add_new_address saves with this flag.
	address.save(ignore_permissions=True)
	return {"name": address.name, "address_type": address.address_type}
