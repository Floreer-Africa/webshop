// Renders shipping panels on a portal order page (PR-Foundry/framework#229).
//
// THE SEAM. Mounts by finding an anchor in the rendered page, NOT by editing
// templates/pages/order.html. webshop is an upstream fork here, so a template we patch is a
// line the next sync resets and a re-verify grep has to watch. This way upstream-owned
// lines stay at zero — the same choice made for the checkout address form.
//
// Panels come from `webshop.webshop.portal.shipping_panels.get_shipping_panels`, which
// aggregates every app that registered the `webshop_shipping_panels` hook. This file knows
// nothing about any carrier: a second shipping app appears here by registering, with no
// change to this bundle.
//
// EVERY contributed value is written with textContent, never innerHTML. A carrier's
// tracking string is attacker-influenced data arriving through a third-party app, and this
// page is a public storefront.

frappe.provide("webshop.portal_shipping");

webshop.portal_shipping = {
	// The order page renders one of these; both carry the doctype and name we need.
	REFERENCE_SELECTOR: "[data-doctype][data-docname]",

	reference() {
		const el = document.querySelector(webshop.portal_shipping.REFERENCE_SELECTOR);
		if (el) {
			return { doctype: el.getAttribute("data-doctype"), name: el.getAttribute("data-docname") };
		}
		// Fall back to the route: /orders/<name> and /shipments/<name> are webshop's own
		// portal list routes.
		const match = window.location.pathname.match(/^\/(orders|shipments)\/([^/?#]+)/);
		if (!match) return null;
		return {
			doctype: match[1] === "orders" ? "Sales Order" : "Delivery Note",
			name: decodeURIComponent(match[2]),
		};
	},

	host() {
		const existing = document.querySelector(".webshop-shipping-panels");
		if (existing) return existing;
		// Sits after the page's main card, before the footer, so it reads as part of the
		// order rather than as a floating box.
		const anchor =
			document.querySelector(".page_content .frappe-card:last-of-type") ||
			document.querySelector(".page_content") ||
			document.querySelector("main");
		if (!anchor) return null;
		const host = document.createElement("div");
		host.className = "webshop-shipping-panels mt-4";
		anchor.parentNode.insertBefore(host, anchor.nextSibling);
		return host;
	},

	render(host, panels) {
		host.textContent = "";
		panels.forEach((panel) => {
			const card = document.createElement("div");
			card.className = "mb-3 frappe-card p-5";

			const head = document.createElement("div");
			head.className = "d-flex justify-content-between align-items-center";
			const title = document.createElement("h6");
			title.className = "mb-0";
			title.textContent = panel.title || "";
			head.appendChild(title);
			if (panel.status) {
				const badge = document.createElement("span");
				badge.className = "small text-muted";
				badge.textContent = panel.status;
				head.appendChild(badge);
			}
			card.appendChild(head);
			card.appendChild(document.createElement("hr"));

			(panel.rows || []).forEach((row) => {
				const line = document.createElement("div");
				line.className = "d-flex justify-content-between small mb-1";
				const label = document.createElement("span");
				label.className = "text-muted";
				label.textContent = row.label || "";
				const value = document.createElement("span");
				value.className = "text-right";
				// textContent, never innerHTML. See the header.
				value.textContent = row.value || "";
				line.append(label, value);
				card.appendChild(line);
			});

			if (panel.note) {
				const note = document.createElement("div");
				note.className = "small text-muted mt-2";
				note.textContent = panel.note;
				card.appendChild(note);
			}
			host.appendChild(card);
		});
	},

	mount() {
		const reference = webshop.portal_shipping.reference();
		if (!reference) return;
		frappe.call({
			method: "webshop.webshop.portal.shipping_panels.get_shipping_panels",
			args: reference,
			callback: (r) => {
				const panels = (r && r.message) || [];
				// No panel is the common case -- most orders are not shipped by an app that
				// registered one -- so nothing is inserted at all rather than an empty box.
				if (!panels.length) return;
				const host = webshop.portal_shipping.host();
				if (host) webshop.portal_shipping.render(host, panels);
			},
			// A failure here must leave the order page exactly as it was: the customer came
			// to read their order, not their parcel.
			error: () => {},
		});
	},
};

frappe.ready(() => {
	if (!/^\/(orders|shipments)\//.test(window.location.pathname)) return;
	webshop.portal_shipping.mount();
});
