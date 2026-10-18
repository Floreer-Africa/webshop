"""The product-page inquiry, without handing a Lead back to the visitor.

PR-Foundry fork addition (framework#277), registered through ``override_whitelisted_methods``
like ``checkout_address.py`` so no upstream-owned file changes.

Upstream's ``cart.create_lead_for_item_inquiry`` is ``allow_guest``. When the email already
belongs to a Lead it falls back to that Lead and **returns the whole document** -- an
anonymous visitor who knew a customer's email got their name, company, phone and notes. It
also writes the visitor's subject and message into the Lead's comment as raw HTML, which staff
then open in desk.

It no longer runs at all on ERPNext v16: it inserts a ``Lead Source``, a doctype erpnext's
``v15_0.migrate_to_utm_analytics`` patch removed in favour of ``UTM Source``, so every inquiry
raised before the Lead was saved. This replacement keeps the behaviour the product page
expects (create the Lead, or annotate the existing one) on the v16 field.
"""

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import escape_html

_SOURCE = "Product Inquiry"
_LEAD_FIELDS = ("lead_name", "company_name", "email_id", "phone")


def _ensure_source() -> str:
	if not frappe.db.exists("UTM Source", _SOURCE):
		frappe.get_doc({"doctype": "UTM Source", "__newname": _SOURCE}).insert(ignore_permissions=True)
	return _SOURCE


# Open to anyone and it writes (a Lead, a comment), so it is throttled per IP like the
# app's other guest writes. A visitor sends one inquiry at a time.
INQUIRY_RATE = {"limit": 5, "seconds": 60}


@frappe.whitelist(allow_guest=True)
@rate_limit(**INQUIRY_RATE)
def create_lead_for_item_inquiry(lead: str | dict, subject: str, message: str) -> bool:
	"""Record a product inquiry against a Lead. Returns only ``True``.

	The form reads the reply as truthy and nothing else, so nothing about any Lead is
	returned -- in particular not one an anonymous caller merely named by email.
	"""
	lead = frappe.parse_json(lead) or {}
	email = (lead.get("email_id") or "").strip()

	existing = frappe.db.get_value("Lead", {"email_id": email}) if email else None
	if existing:
		lead_doc = frappe.get_doc("Lead", existing)
	else:
		lead_doc = frappe.new_doc("Lead")
		for fieldname in _LEAD_FIELDS:
			lead_doc.set(fieldname, lead.get(fieldname))
		lead_doc.set("lead_owner", "")
		lead_doc.set("utm_source", _ensure_source())
		lead_doc.insert(ignore_permissions=True)

	lead_doc.add_comment(
		"Comment",
		text=f"<div><h5>{escape_html(subject or '')}</h5><p>{escape_html(message or '')}</p></div>",
	)
	return True
