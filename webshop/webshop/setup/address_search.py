"""Webshop Settings field for restricting the checkout address search by country.

PR-Foundry fork addition. Added as a **Custom Field** rather than by editing
``webshop_settings.json``: that file is upstream-owned, so every line changed in it is a
line a sync can reset and a re-verify grep has to watch. A Custom Field keeps that surface
at zero, the same choice made for the address form's seam and its server contract.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDNAME = "custom_address_search_countries"
CHILD_DOCTYPE = "Webshop Address Country"

# Google takes at most 15 CLDR region codes in includedRegionCodes.
MAX_REGION_CODES = 15

ADDRESS_SEARCH_FIELDS = {
	"Webshop Settings": [
		{
			"fieldname": FIELDNAME,
			"label": "Address Search Countries",
			"fieldtype": "Table MultiSelect",
			"options": CHILD_DOCTYPE,
			"insert_after": "enable_checkout",
			"description": (
				"Limit checkout address suggestions to these countries. "
				"Leave empty to search worldwide. At most 15."
			),
		}
	]
}


def ensure_address_search_field() -> str:
	create_custom_fields(ADDRESS_SEARCH_FIELDS, ignore_validate=True)
	return "ok"


def after_migrate():
	ensure_address_search_field()


def validate_country_limit(doc, method=None):
	"""Refuse more than Google will accept, at save.

	Truncating silently would ignore countries the operator deliberately chose, and the
	symptom would surface far from the cause -- customers in the dropped countries simply
	not finding their address, with nothing anywhere saying why.
	"""
	countries = doc.get(FIELDNAME) or []
	if len(countries) > MAX_REGION_CODES:
		frappe.throw(
			_(
				"Address Search Countries accepts at most {0} countries; {1} are selected. "
				"Google's address search does not accept more, so the extra ones would be "
				"ignored without warning."
			).format(MAX_REGION_CODES, len(countries)),
			frappe.ValidationError,
		)
