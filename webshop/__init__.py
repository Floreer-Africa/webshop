import frappe

__version__ = "0.0.1"


def check_app_permission():
	"""Apps-screen gate: staff only (framework#247).

	A tile with no gate is offered to every user, and ``frappe.apps.get_default_path``
	turns a Website User's visible ``/desk/*`` tiles into a ``/desk`` post-login and
	post-reset landing, which ``www/desk.py`` refuses outright.
	"""
	from frappe.utils.user import is_website_user

	if frappe.session.user == "Administrator":
		return True

	return not is_website_user()
