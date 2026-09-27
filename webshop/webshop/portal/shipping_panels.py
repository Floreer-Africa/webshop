"""A seam for shipping apps to say where a parcel is (PR-Foundry/framework#229).

PR-Foundry fork addition. Upstream webshop has no file of this name, so it cannot conflict
on a sync.

A portal order page shows the order and its attachments and stops there. A shipping app has
nowhere to tell the customer where their parcel is, and webshop's order template is
upstream-owned — so without a seam, each shipping app's only route is to fork that template
and watch it diverge on the next sync. One app doing that is a maintenance cost; three doing
it is three incompatible forks of the same file.

**The contract.** An app registers a dotted path and returns structured data:

    # any shipping app's hooks.py
    webshop_shipping_panels = ["courier_guy_za.portal.collection.panel"]

    def panel(doctype: str, name: str) -> dict | None:
        '''None when this app has nothing to say about this document.'''
        return {"title": ..., "status": ..., "rows": [{"label": ..., "value": ...}]}

**Data, never markup.** Contributors return labels and values; the bundle renders them with
``textContent``. An app returning HTML would make every other app's panel an XSS surface on
a public storefront — and "it's a trusted app" is not a boundary, because a carrier's
tracking string is attacker-influenced data arriving *through* that app.
"""

from __future__ import annotations

import frappe
from frappe import _

HOOK = "webshop_shipping_panels"

# What a contributor may put on a customer's page. Anything else it returns is dropped
# rather than passed through -- an `html` key would be a renderer's standing temptation.
_ALLOWED_KEYS = ("title", "status", "rows", "note")


def _clean(panel: dict) -> dict | None:
	"""Keep only the contract's keys, and only when there is something to show."""
	if not isinstance(panel, dict):
		return None
	out = {k: panel[k] for k in _ALLOWED_KEYS if k in panel}
	if not out.get("title"):
		return None
	rows = out.get("rows") or []
	out["rows"] = [
		{"label": str(r.get("label") or ""), "value": str(r.get("value") or "")}
		for r in rows
		if isinstance(r, dict)
	]
	return out


@frappe.whitelist()
def get_shipping_panels(doctype: str, name: str) -> list[dict]:
	"""Every registered shipping app's panel for one document the caller owns.

	Gated on ``has_website_permission`` -- the permission a portal customer actually holds
	-- and gated **before** any contributor runs. A contributor that runs first has already
	read the document, and may have logged it, whatever this returns afterwards.

	A missing document raises the **same** ``PermissionError`` as one the caller does not
	own: distinguishing them lets a logged-in caller enumerate real order names by probing
	responses (the framework#107 lesson).
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in."), frappe.PermissionError)

	if not frappe.db.exists(doctype, name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc(doctype, name)
	if not frappe.has_website_permission(doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	panels: list[dict] = []
	for method in frappe.get_hooks(HOOK) or []:
		try:
			contributed = (
				frappe.call(method, doctype=doctype, name=name)
				if isinstance(method, str)
				else method(doctype, name)
			)
		except Exception:
			# One shipping app raising must not take the order page down with it -- least
			# of all another app's panel, which is the part the customer came for.
			frappe.log_error(
				title="webshop: a shipping panel failed",
				message=f"{method} on {doctype} {name}\n" + frappe.get_traceback(),
			)
			continue
		cleaned = _clean(contributed)
		if cleaned:
			panels.append(cleaned)
	return panels
