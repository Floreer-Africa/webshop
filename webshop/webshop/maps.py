"""Map/geocoding configuration for the checkout address form.

PR-Foundry fork addition (checkout address form design, 2026-09-24). Upstream webshop has
no file of this name, so it cannot conflict on a sync.

Deliberately a top-level module and NOT ``webshop/webshop/api/maps.py``: upstream already
ships ``webshop/webshop/api.py``, and adding an ``api/`` package next to it makes Python
resolve the package and silently hide the module. That took out
``webshop.webshop.api.get_guest_redirect_on_action`` and broke guest add-to-cart. Guarded by
``client_app.tests.test_places_key.TestUpstreamApiModuleIsNotShadowed``.
"""

import frappe


@frappe.whitelist(allow_guest=True)
def get_places_key() -> str | None:
	"""The Google browser API key for Places autocomplete, or ``None`` when unconfigured.

	``allow_guest`` because a webshop checkout runs before login.

	Returning a key to the page is deliberate and not a leak: ``Google Settings.api_key``
	is a *browser* key by Google's definition and by frappe's own field description ("The
	browser API key obtained from the Google Cloud Console"), and a browser key is only
	ever usable from a page. What stops it being spent by someone else is the HTTP-referrer
	restriction set in the Cloud console -- withholding it from the page that must use it
	protects nothing and simply breaks the feature.

	Returns ``None`` when the integration is disabled or the key is blank, so the caller
	degrades to manual address entry rather than loading a script that will fail.
	"""
	settings = frappe.get_cached_doc("Google Settings")
	if not settings.enable:
		return None
	return (settings.api_key or "").strip() or None


@frappe.whitelist(allow_guest=True)
def get_address_search_config() -> dict:
	"""Everything the checkout address search needs, in one round trip.

	``region_codes`` are CLDR two-letter codes for Google's ``includedRegionCodes``. An
	empty list means no restriction -- Google's own semantics and the shop's default.

	``Country.code`` is already lowercase ISO 3166-1 alpha-2, which is what CLDR region
	codes are, so nothing maps between them. A country carrying no code is skipped rather
	than sent as an empty string, which Google would reject for the whole request and take
	the other countries down with it.
	"""
	from webshop.webshop.setup.address_search import FIELDNAME, MAX_REGION_CODES

	selected = frappe.get_cached_doc("Webshop Settings").get(FIELDNAME) or []
	codes = []
	for row in selected:
		code = (frappe.db.get_value("Country", row.country, "code") or "").strip().lower()
		if code:
			codes.append(code)

	return {
		"key": get_places_key(),
		# Bounded here as well as at save. The save guard can be bypassed by a direct
		# db write, and one country too many makes Google reject the request entirely --
		# so the checkout degrades to unrestricted rather than to no search at all.
		"region_codes": codes[:MAX_REGION_CODES],
	}
