# Copyright (c) 2026, PR-Foundry and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WebshopAddressCountry(Document):
	"""One country the checkout address search is allowed to return results from.

	A child table rather than a comma-separated field so the operator picks real Country
	records and the values validate themselves. ``Country.code`` is already the CLDR
	two-letter region code Google wants, so nothing maps between them.
	"""

	pass
