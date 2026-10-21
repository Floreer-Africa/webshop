"""Portal "Pay" endpoint for logged-in webshop customers and suppliers.

PR-Foundry/framework#182 (fork marker).

ERPNext's ``make_payment_request`` gates on **two** doctype permissions, in this order::

    frappe.has_permission("Payment Request", "create", throw=True)  # doctype-INDEPENDENT
    frappe.has_permission(args.dt, "read", args.dn, throw=True)  # per reference doctype

A real portal user's roles are ``['All', 'Customer', 'Guest']`` (``Portal Settings.default_role``
is ``Customer``), and erpnext ships **no** permission row granting ``Customer`` anything on
Payment Request, Sales Invoice or Sales Order. ``frappe.has_permission`` consults role, user and
share permissions only -- never website permission -- so **both** gates fail, for **every**
reference doctype. The native order-page "Pay" link therefore 403s for exactly the customers the
on-account flow exists to serve.

What a portal user *does* hold is ``has_website_permission`` on their own document, backed by a
``Portal User`` row on their Customer (``erpnext.controllers.website_list_for_contact``). This
module gates on that -- the permission they actually have -- and only then elevates so
``make_payment_request``'s own doctype checks pass. The ownership gate always runs *before* any
elevation, so a user can never pay another party's document.

Why this lives in **webshop** and not in a client app: webshop owns the template that calls it and
is forked by every sibling from PR-Foundry, so siblings inherit one implementation. The previous
per-tier wrappers (``client_app.api.portal.pay_invoice`` here,
``client_app.api.guest_checkout.pay_for_order`` at OA-Method) each lived in a *client-specific*
app, which is precisely why the shared template diverged and why a sibling could not resolve the
function the template named.

PR-Foundry/framework#109 (fork marker): the endpoint creates and submits a Payment Request, so it
acts only on a POST, which frappe refuses without the session's CSRF token. The order page submits
a form carrying that token. A GET (a bookmark, an old email, the browser's back button) creates
nothing: it is redirected to the document's portal page, where the customer presses Pay.
"""

from urllib.parse import quote

import frappe
from erpnext.accounts.doctype.payment_request.payment_request import (
	ALLOWED_DOCTYPES_FOR_PAYMENT_REQUEST,
	get_amount,
	make_payment_request,
)
from frappe import _
from frappe.utils import flt, validate_email_address

# erpnext decides the Payment Request direction from exactly these two doctypes
# ("payment_request_type = 'Outward' if args.get('dt') in ['Purchase Order', 'Purchase Invoice']").
# The party side is derived the same way rather than classified a second time here.
_SUPPLIER_SIDE_DOCTYPES = ("Purchase Order", "Purchase Invoice")


def amount_due(doc) -> float:
	"""Return what erpnext would actually charge for ``doc`` right now, else ``0.0``.

	This delegates to erpnext's own :func:`get_amount` -- the very function
	``make_payment_request`` uses to set the Payment Request's ``grand_total``. Asking the
	*charging* function whether there is anything to charge is what keeps the affordance and
	the charge from drifting apart: the button is offered exactly when a non-zero amount would
	be requested.

	It also removes the per-doctype hand-rolled conditions this bug came from. ``get_amount``
	already handles both shapes, currency conversion included:

	* Sales/Purchase Order -- ``(rounded_total or grand_total) - flt(advance_paid)``; ``flt``
	  maps a ``None`` ``advance_paid`` (its value before any payment) to ``0.0``.
	* Sales/Purchase Invoice -- driven by ``outstanding_amount``.

	Fails **closed** (returns ``0.0``) if erpnext cannot value the document. A hidden Pay button
	costs the customer a phone call; a Pay button shown on a settled document is a real double
	charge (framework#183), so the safe direction is not symmetric.
	"""
	if doc.doctype not in ALLOWED_DOCTYPES_FOR_PAYMENT_REQUEST:
		return 0.0

	try:
		return flt(get_amount(doc))
	# Deliberately broad, and the breadth IS the behaviour: get_amount reaches into
	# erpnext's pricing for two doctype shapes, so the failure modes are open-ended. A
	# hidden Pay button costs the customer a phone call; a Pay button on a settled
	# document is a real double charge (framework#183), so this fails CLOSED on anything.
	except Exception:
		frappe.log_error(
			title="webshop: could not value document for portal payment",
			message=f"{doc.doctype} {doc.name}: {frappe.get_traceback()}",
		)
		return 0.0


def is_payable(doc) -> bool:
	"""Return True when ``doc`` still owes money and erpnext can raise a Payment Request for it."""
	return amount_due(doc) > 0


def _party_for(doc) -> tuple[str, str | None]:
	party_type = "Supplier" if doc.doctype in _SUPPLIER_SIDE_DOCTYPES else "Customer"
	return party_type, doc.get(party_type.lower())


def _valid_email(value) -> str | None:
	"""Return ``value`` if it is a real email address, else ``None``.

	Delegates to frappe's own validator rather than testing for ``"@"``, so a login that
	merely contains one cannot pass for an address.
	"""
	return validate_email_address((value or "").strip(), throw=False) or None


def _party_contact_email(doc) -> str | None:
	"""The email on the document's contact person, else the party's default contact."""
	from frappe.contacts.doctype.contact.contact import get_default_contact

	party_type, party = _party_for(doc)
	if not party:
		return None
	contact = doc.get("contact_person") or get_default_contact(party_type, party)
	if not contact:
		return None
	return frappe.db.get_value("Contact", contact, "email_id")


def _payer_email(doc, session_user: str) -> str | None:
	"""Resolve the buyer's email from the DOCUMENT, never from whoever owns the row.

	erpnext falls back to ``ref_doc.owner`` when no ``recipient_id`` is supplied
	(``payment_request.py:930``). Since upstream webshop ``80588995e0`` -- named, exactly,
	"create sales transactions as Admin" -- ``place_order`` submits the cart Quotation inside
	``system_permissions()``, so a portal order is owned by **Administrator** and that fallback
	yields the literal string ``"Administrator"``. PayFast rejects it with a 400; a gateway
	that does not validate simply records a non-address as the payer. PR-Foundry/framework#225.

	It only ever worked because the owner happened to be a login shaped like an email. On a
	site whose usernames are not addresses it has been wrong since this code was written.

	Resolution order -- the document first, the caller's identity only as a last resort:

	1. ``contact_email``: the address the order was actually placed with;
	2. the contact person's / party's default contact email;
	3. the caller's own login, and only when it is a real address.

	Step 3 is why this MUST be called **before** any elevation: read after
	``frappe.set_user("Administrator")`` it would reproduce the defect exactly.
	"""
	for candidate in (doc.get("contact_email"), _party_contact_email(doc), session_user):
		email = _valid_email(candidate)
		if email:
			return email
	return None


def document_page_url(dt: str, dn: str) -> str:
	"""The portal page that shows ``dn`` (``/orders/<name>``, ``/invoices/<name>``, ...).

	Read off the ``website_route_rules`` that route to the ``order`` page, so it cannot drift
	from the routes the site actually serves. ``/me`` when no rule names the doctype.
	"""
	for rule in frappe.get_hooks("website_route_rules"):
		if rule.get("to_route") != "order" or (rule.get("defaults") or {}).get("doctype") != dt:
			continue
		prefix = rule.get("from_route", "").split("/<", 1)[0]
		if prefix:
			return f"{prefix}/{quote(str(dn), safe='')}"
	return "/me"


def _is_http_get() -> bool:
	"""True only inside an HTTP request that is not a POST.

	In-process callers (tests, ``bench execute``) have no request and are server code, so they
	are not redirected. The whitelist below admits GET and POST only.
	"""
	request = getattr(frappe.local, "request", None)
	return request is not None and request.method != "POST"


# PR-Foundry/framework#109: GET is admitted only so that a link already in the wild lands
# somewhere useful instead of on frappe's bare 405. It never creates anything.
@frappe.whitelist(methods=["GET", "POST"])  # login required (NOT allow_guest); Guest refused below
def pay_for_document(dt: str, dn: str):
	"""Create (and redirect to) a gateway Payment Request for the caller's own document.

	POST only does that. frappe validates the CSRF token on every POST from a logged-in
	session, so a page on another site cannot make the customer's browser raise a Payment
	Request. A GET is redirected to the document's portal page and changes nothing
	(framework#109).

	Args:
	        dt: reference doctype (must be payable per ``ALLOWED_DOCTYPES_FOR_PAYMENT_REQUEST``).
	        dn: reference document name; the caller must own it via website permission.

	Returns:
	        The ``make_payment_request`` result. With ``order_type="Shopping Cart"`` that call sets
	        an HTTP redirect to the gateway checkout, which is the intended "Pay" behaviour.

	Raises:
	        frappe.PermissionError: caller is Guest, or does not own ``dn``.
	        frappe.ValidationError: ``dt`` is not payable, or nothing is owed.
	"""
	if _is_http_get():
		# No lookup at all: the redirect is the same for any name, so it reveals nothing, and
		# the order page does its own permission check (a Guest is sent to log in there).
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = document_page_url(dt, dn)
		return None

	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to pay."), frappe.PermissionError)

	# Imported from erpnext rather than re-declared, so the payable set cannot drift from the
	# one make_payment_request itself enforces.
	if dt not in ALLOWED_DOCTYPES_FOR_PAYMENT_REQUEST:
		frappe.throw(
			_("Payment Requests cannot be created against: {0}").format(frappe.bold(dt)),
			frappe.ValidationError,
		)

	# Existence check BEFORE get_doc, raising the SAME error a valid-but-unowned document gets.
	# frappe.get_doc() raises DoesNotExistError for a missing name, which is distinguishable
	# from PermissionError -- that difference would let a logged-in caller enumerate real
	# document names by probing responses.
	if not frappe.db.exists(dt, dn):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc(dt, dn)

	# Ownership gate -- MUST run before any elevation. frappe.has_website_permission fails
	# CLOSED (returns False when the doctype has neither a has_website_permission hook nor a
	# controller method), so a payable doctype with no website-permission handler -- POS Invoice,
	# Fees -- is refused by construction rather than by an allowlist someone has to maintain.
	if not frappe.has_website_permission(doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# Server-side twin of the template's gate. The affordance is not the control: this endpoint
	# is directly reachable, and a settled document must not be chargeable from a stale link
	# (framework#183, and the framework#149 lesson that a caller-side gate alone is not enough).
	if not is_payable(doc):
		frappe.throw(_("This document has no outstanding balance."), frappe.ValidationError)

	party_type, party = _party_for(doc)

	# Resolved BEFORE elevation -- see _payer_email. Passing it as recipient_id is what stops
	# erpnext falling back to ref_doc.owner, which on a portal order is "Administrator"
	# (framework#225).
	payer_email = _payer_email(doc, frappe.session.user)
	if not payer_email:
		# Refuse rather than proceed: recipient_id=None falls straight back to the owner, and
		# email_to is also the payment-request email recipient (payment_request.py:647). A
		# refusal the customer can report beats a 400 at the gateway with nothing logged here.
		frappe.throw(
			_("We do not have an email address for this order. Please contact us to arrange payment."),
			frappe.ValidationError,
		)

	# Elevate ONLY after the ownership gate above passed -- and through system_permissions,
	# never frappe.set_user: set_user also sets session.sid to the user NAME, so restoring
	# the user afterwards left the customer's cookie holding their email address, and the
	# next page logged them out (framework#255).
	from webshop.webshop.shopping_cart.cart import system_permissions

	with system_permissions():
		return make_payment_request(
			dt=dt,
			dn=dn,
			submit_doc=1,
			order_type="Shopping Cart",
			party_type=party_type,
			party=party,
			recipient_id=payer_email,
		)
