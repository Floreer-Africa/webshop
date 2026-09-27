// The checkout address form.
//
// PR-Foundry fork addition. Replaces webshop's native "New Address" dialog with one form
// that captures everything a delivery actually needs: an international phone, an email, and
// (from Task 6) a Google-autocompleted address carrying coordinates -- because TCG publishes
// no geocoding endpoint, so an L2D booking's lat/lng has to come from us.
//
// THE SEAM. This takes over by rebinding `.btn-new-address`, NOT by editing
// templates/includes/cart/cart_address.html. webshop is an upstream fork here; a template we
// copy or patch diverges silently on the next sync, which is the lesson already recorded
// against the locker picker. A rebind keeps the fork-patch surface in upstream-owned files at
// zero lines.
//
// The price of that choice is a silent failure mode: if upstream renames the class, this binds
// to nothing and the native dialog quietly returns. That is why
// client_app.tests.test_checkout_address_seam exists and why it checks both that the class is
// present AND that upstream still binds a click to it.

frappe.provide("webshop.checkout_address");

webshop.checkout_address = {
	VENDOR: "/assets/webshop/vendor/intl-tel-input",
	_vendor: null,

	// -- lazy vendor loading ------------------------------------------------------------
	//
	// intl-tel-input's WithUtils build is 316 KB, taken deliberately because getNumber()
	// (E.164) and isValidNumber() both live in the utils half. It is fetched when a customer
	// opens this form and never on page load, so a visitor who never enters an address never
	// pays for it.

	loadStyle(href) {
		if (document.querySelector(`link[href="${href}"]`)) return;
		const link = document.createElement("link");
		link.rel = "stylesheet";
		link.href = href;
		document.head.appendChild(link);
	},

	loadScript(src) {
		return new Promise((resolve, reject) => {
			const existing = document.querySelector(`script[src="${src}"]`);
			if (existing) {
				if (existing.dataset.loaded) return resolve();
				existing.addEventListener("load", () => resolve());
				existing.addEventListener("error", reject);
				return;
			}
			const script = document.createElement("script");
			script.src = src;
			script.addEventListener("load", () => {
				script.dataset.loaded = "1";
				resolve();
			});
			script.addEventListener("error", reject);
			document.head.appendChild(script);
		});
	},

	async ensureVendor() {
		if (webshop.checkout_address._vendor) return webshop.checkout_address._vendor;
		const base = webshop.checkout_address.VENDOR;
		webshop.checkout_address.loadStyle(`${base}/css/intlTelInput.min.css`);
		webshop.checkout_address._vendor = webshop.checkout_address
			.loadScript(`${base}/js/intlTelInputWithUtils.min.js`)
			.catch((e) => {
				// Reset so a later attempt can retry rather than being stuck on a rejected
				// promise, and let the caller decide -- the form must still open.
				webshop.checkout_address._vendor = null;
				throw e;
			});
		return webshop.checkout_address._vendor;
	},

	// -- the seam ----------------------------------------------------------------------

	takeOver() {
		const $btn = $(`.${webshop.checkout_address.HOOK_CLASS}`);
		if (!$btn.length) return false;
		$btn.off("click").on("click", (e) => {
			e.preventDefault();
			webshop.checkout_address.open($(e.currentTarget));
		});
		return true;
	},

	HOOK_CLASS: "btn-new-address",

	// -- the form ----------------------------------------------------------------------

	// Which section the button sits in decides the address type, instead of asking the
	// customer to classify their own address. The native dialog made it a required choice.
	typeFor($btn) {
		const section = $btn.closest("[data-section]").attr("data-section") || "";
		return section.indexOf("billing") !== -1 ? "Billing" : "Shipping";
	},

	fields(addressType) {
		return [
			{
				fieldname: "wsa_lookup",
				fieldtype: "HTML",
				options: `<div class="wsa-lookup mb-3"></div>`,
			},
			{ label: __("Address Title"), fieldname: "address_title", fieldtype: "Data", reqd: 1 },
			{ label: __("Address Line 1"), fieldname: "address_line1", fieldtype: "Data", reqd: 1 },
			{ label: __("Address Line 2"), fieldname: "address_line2", fieldtype: "Data" },
			{ label: __("City/Town"), fieldname: "city", fieldtype: "Data", reqd: 1 },
			{ label: __("Province / State"), fieldname: "state", fieldtype: "Data" },
			{
				// Required here where upstream left it optional: the postal code is what
				// decides courier serviceability, so a blank one fails later and less
				// legibly than an empty box does now.
				label: __("Postal Code"),
				fieldname: "pincode",
				fieldtype: "Data",
				reqd: 1,
			},
			{
				label: __("Country"),
				fieldname: "country",
				fieldtype: "Link",
				options: "Country",
				only_select: true,
				reqd: 1,
			},
			{ fieldname: "col", fieldtype: "Column Break" },
			{
				// The label carries frappe's own `reqd` marker class
				// (.control-label.reqd:after in controls.scss) so the asterisk matches the
				// real fields exactly instead of being a hand-drawn imitation beside them.
				// The field IS required -- the server refuses an address with no number --
				// and a required field that does not look required is a form that lies.
				fieldname: "wsa_phone",
				fieldtype: "HTML",
				options: `
					<div class="form-group">
						<label class="control-label reqd" for="wsa-phone-input">${__("Mobile number")}</label>
						<input type="tel" id="wsa-phone-input" class="form-control wsa-phone-input"
							autocomplete="tel">
						<div class="small text-muted mt-1">${__(
							"Used for delivery notifications, including a locker collection PIN.",
						)}</div>
						<div class="small text-danger mt-1 wsa-phone-error" hidden></div>
					</div>`,
			},
			{
				label: __("Email"),
				fieldname: "email_id",
				fieldtype: "Data",
				options: "Email",
				reqd: 1,
				description: __("Delivery updates are sent here."),
			},
			{
				label: __("Address Type"),
				fieldname: "address_type",
				fieldtype: "Select",
				options: ["Billing", "Shipping"],
				default: addressType,
				reqd: 1,
			},
		];
	},

	async open($btn) {
		const addressType = webshop.checkout_address.typeFor($btn);

		// The vendor load is awaited but never allowed to stop the form opening: a phone
		// field without the flag widget is still a usable phone field, and a checkout that
		// cannot proceed because an asset failed is worse than a plainer input.
		let vendorOk = true;
		try {
			await webshop.checkout_address.ensureVendor();
		} catch (e) {
			vendorOk = false;
			console.warn("checkout address: phone widget unavailable, using a plain input", e);
		}

		const d = new frappe.ui.Dialog({
			title: __("Delivery Address"),
			fields: webshop.checkout_address.fields(addressType),
			primary_action_label: __("Save address"),
			primary_action: (values) => webshop.checkout_address.submit(d, values),
		});

		d.show();
		webshop.checkout_address._dialog = d;
		webshop.checkout_address._vendorOk = vendorOk;
		webshop.checkout_address.attachPhone(d, vendorOk);
		webshop.checkout_address.attachLookup(d);
		$(document).trigger("webshop:address-form-shown", [d, { vendorOk, addressType }]);
	},

	// -- address lookup ------------------------------------------------------------------
	//
	// Google Places. NEVER a gate: with no key, a blocked script, an offline customer or an
	// API error, every field stays manually editable and the form submits exactly as it did
	// before. A checkout that cannot complete because a third party is down would be a worse
	// defect than the typing this saves.
	//
	// Uses PlaceAutocompleteElement, not google.maps.places.Autocomplete. The legacy Places
	// service "will not be available in new Cloud projects" (Google's deprecation page,
	// transition 1 March 2025), so the widget most examples still show cannot work for a key
	// issued today.

	// Resolves true once `test()` does, or false after `timeoutMs`. Bounded on purpose:
	// an unbounded wait on a third party is a checkout that hangs.
	waitFor(test, timeoutMs) {
		return new Promise((resolve) => {
			const started = Date.now();
			(function poll() {
				if (test()) return resolve(true);
				if (Date.now() - started > timeoutMs) return resolve(false);
				setTimeout(poll, 50);
			})();
		});
	},

	async loadPlaces() {
		// Fetched even when Google is already loaded: the region list is configuration and
		// can change between opens, while the script is loaded once per page.
		const r = await frappe.call("webshop.webshop.maps.get_address_search_config");
		const cfg = (r && r.message) || {};
		webshop.checkout_address._regions = cfg.region_codes || [];
		if (window.google && window.google.maps && window.google.maps.importLibrary) return true;
		const key = cfg.key;
		if (!key) return false;
		await webshop.checkout_address.loadScript(
			"https://maps.googleapis.com/maps/api/js?" +
				$.param({ key, v: "weekly", libraries: "places", loading: "async" }),
		);
		// The loading=async bootstrap finishes defining google.maps.importLibrary AFTER the
		// outer script's load event, so testing for it immediately is a race -- and one that
		// loses the first time and wins afterwards, which is the worst shape. Observed on a
		// clean browser with no extensions: the first open said "unavailable", closing and
		// reopening showed the search box, because by then Google had finished and the
		// early-return at the top of this function found it already there.
		return await webshop.checkout_address.waitFor(
			() => window.google && window.google.maps && window.google.maps.importLibrary,
			8000,
		);
	},

	// Says why the search box is absent instead of leaving a blank space. A silent
	// fallback is how a broken integration looks exactly like one that was never
	// configured, and the customer is left wondering whether to wait or start typing.
	lookupUnavailable(host, reason) {
		if (!host) return;
		const note = document.createElement("div");
		note.className = "small text-muted mb-2 wsa-lookup-note";
		note.textContent = __("Address search is unavailable — please enter your address below.");
		if (reason) note.title = String(reason).slice(0, 200);
		host.appendChild(note);
	},

	async attachLookup(d) {
		const host = d.$wrapper.find(".wsa-lookup")[0];
		if (!host) return;
		let ok = false;
		let why = null;
		try {
			ok = await webshop.checkout_address.loadPlaces();
			if (!ok) why = "no API key configured";
		} catch (e) {
			why = e;
			console.warn("checkout address: place lookup unavailable, enter manually", e);
		}
		if (!ok) {
			webshop.checkout_address.lookupUnavailable(host, why);
			return;
		}

		try {
			const { PlaceAutocompleteElement } = await google.maps.importLibrary("places");
			// Empty means worldwide -- Google's own semantics, so an unrestricted shop
			// passes nothing rather than a sentinel. Set in the constructor because the
			// element reads it when it builds its request.
			const regions = webshop.checkout_address._regions || [];
			const el = new PlaceAutocompleteElement(
				regions.length ? { includedRegionCodes: regions } : {},
			);
			el.style.width = "100%";
			// The element renders its controls inside a shadow root, which follows the
			// BROWSER's colour preference rather than the page's. On a light storefront in
			// a dark-preferring browser that is a black box -- observed. Pinning the scheme
			// on the host is what reaches inside the shadow root; a background on the host
			// alone does not.
			el.style.colorScheme = "light";
			host.appendChild(el);

			// Both names are bound deliberately: the event was gmp-placeselect while the
			// element was in beta and gmp-select at GA. Binding one and guessing wrong is a
			// lookup that renders, accepts a click, and does nothing.
			const onSelect = async (event) => {
				try {
					const prediction = event.placePrediction || (event.detail || {}).placePrediction;
					if (!prediction) return;
					const place = prediction.toPlace();
					await place.fetchFields({
						fields: ["addressComponents", "location", "id", "formattedAddress"],
					});
					webshop.checkout_address.applyPlace(d, place);
				} catch (e) {
					console.warn("checkout address: could not read the selected place", e);
				}
			};
			el.addEventListener("gmp-select", onSelect);
			el.addEventListener("gmp-placeselect", onSelect);
		} catch (e) {
			// Google reports a bad key, a disabled API, a blocked referrer or missing
			// billing by THROWING here, so this is the branch that fires when the Cloud
			// project is misconfigured -- the most likely reason the box never appears.
			console.warn("checkout address: place lookup could not start", e);
			webshop.checkout_address.lookupUnavailable(host, e);
		}
	},

	// Google's component types -> Address fields.
	applyPlace(d, place) {
		const part = (type, prefer) => {
			const c = (place.addressComponents || []).find(
				(x) => (x.types || []).indexOf(type) !== -1,
			);
			if (!c) return "";
			return (prefer === "short" ? c.shortText : c.longText) || c.longText || "";
		};

		const line1 = [part("street_number"), part("route")].filter(Boolean).join(" ");
		// postal_town covers the UK, where locality is often absent.
		const city = part("locality") || part("postal_town") || part("administrative_area_level_2");
		const suburb = part("sublocality_level_1") || part("sublocality") || part("neighborhood");

		const set = (fieldname, value) => {
			if (value) d.set_value(fieldname, value);
		};
		set("address_line1", line1 || place.formattedAddress);
		set("address_line2", suburb);
		set("city", city);
		set("state", part("administrative_area_level_1"));
		set("country", part("country"));
		set("pincode", part("postal_code"));

		const loc = place.location;
		if (loc) {
			webshop.checkout_address._geo = {
				latitude: typeof loc.lat === "function" ? loc.lat() : loc.lat,
				longitude: typeof loc.lng === "function" ? loc.lng() : loc.lng,
				place_id: place.id || "",
			};
		}

		// A place with no postal code is common for rural addresses, and the postal code is
		// what decides courier serviceability -- so ask for it rather than leaving a silent
		// blank that fails later and less legibly.
		if (!part("postal_code")) {
			const $pin = d.get_field("pincode").$input;
			if ($pin && $pin.length) {
				$pin.focus();
				frappe.show_alert({
					message: __("Please add the postal code — we could not find one for that address."),
					indicator: "orange",
				});
			}
		}
	},

	// -- phone ---------------------------------------------------------------------------

	attachPhone(d, vendorOk) {
		webshop.checkout_address._iti = null;
		webshop.checkout_address._geo = null;
		const input = d.$wrapper.find(".wsa-phone-input")[0];
		if (!input) return;

		// No widget is a degraded form, not a broken one: the input stays a plain tel
		// field, whatever is typed goes to the server, and the server refuses anything
		// that is not E.164 with a message naming the format.
		if (!vendorOk || typeof window.intlTelInput !== "function") return;

		webshop.checkout_address._iti = window.intlTelInput(input, {
			// A default, not a restriction -- every country stays selectable. The shop is
			// South African, so that is where an unprompted customer most likely is.
			initialCountry: "za",
			countryOrder: ["za"],
			// Shows the dial code beside the flag rather than inside the input, so what the
			// customer types is their own number as they know it.
			separateDialCode: true,
			// Rejects characters and lengths that cannot belong to the chosen country while
			// typing, rather than only at submit.
			strictMode: true,
		});

		// Options verified present in the vendored 29.5.2 build. nationalMode,
		// preferredCountries and autoPlaceholder are NOT in this major and would be
		// silently ignored if passed.

		d.$wrapper.find(".wsa-phone-input").on("input", () => {
			d.$wrapper.find(".wsa-phone-error").attr("hidden", true);
		});

		d.$wrapper.on("hide.bs.modal", () => {
			const iti = webshop.checkout_address._iti;
			if (iti && typeof iti.destroy === "function") iti.destroy();
			webshop.checkout_address._iti = null;
		});
	},

	// What to send as `phone`, or an error to show. E.164 always: one canonical shape in
	// the database, carrier-specific formatting where a carrier is actually called.
	phoneValue(d) {
		const iti = webshop.checkout_address._iti;
		const $error = d.$wrapper.find(".wsa-phone-error");
		if (!iti) {
			return { number: (d.$wrapper.find(".wsa-phone-input").val() || "").trim() };
		}
		if (!iti.isValidNumber()) {
			$error.text(__("Enter a valid mobile number for the country shown.")).removeAttr("hidden");
			return { error: true };
		}
		$error.attr("hidden", true);
		return { number: iti.getNumber() };
	},

	submit(d, values) {
		// The phone is an HTML field, so frappe's `values` does not carry it.
		const phone = webshop.checkout_address.phoneValue(d);
		if (phone.error) return;
		values.phone = phone.number;

		// Coordinates ride along when a place was picked. Absent for a hand-typed address,
		// which is allowed -- L2D needs them, locker collection does not.
		const geo = webshop.checkout_address._geo;
		if (geo) {
			values.custom_latitude = geo.latitude;
			values.custom_longitude = geo.longitude;
			values.custom_place_id = geo.place_id;
		}

		d.get_primary_btn().prop("disabled", true);
		frappe
			.call("webshop.webshop.shopping_cart.cart.add_new_address", { doc: values })
			.then((r) =>
				frappe.call({
					method: "webshop.webshop.shopping_cart.cart.update_cart_address",
					args: {
						address_type: r.message.address_type,
						address_name: r.message.name,
					},
				}),
			)
			.then(() => {
				d.hide();
				// Reload, as the native dialog does: choosing an address changes the
				// totals, and webshop has no working client-side path to redraw the
				// Payment Summary (shopping_cart.render is called at cart.js:151 and
				// defined nowhere -- framework#223).
				window.location.reload();
			})
			.catch(() => d.get_primary_btn().prop("disabled", false));
	},
};

frappe.ready(() => {
	if (window.location.pathname.replace(/\/$/, "") !== "/cart") return;
	// setTimeout(0) so this runs after upstream's own frappe.ready handler has bound its
	// click. Registration order between apps is not something we control.
	setTimeout(() => webshop.checkout_address.takeOver(), 0);

	// And again whenever the cart re-renders. webshop replaces the address markup in place
	// after a quantity or address change, which destroys the element our click is bound to
	// -- the same re-render that made the locker picker need an observer. Without this the
	// button goes dead (or reverts to upstream's handler) the first time the customer edits
	// anything, which is indistinguishable from the rename failure the seam guard exists to
	// catch, and would be blamed on it.
	//
	// The handler only re-binds. It must never open the form: opening on a mutation would
	// fire on the re-render our own save triggers.
	const host = document.querySelector(".cart-payment-addresses") || document.body;
	new MutationObserver(
		frappe.utils.debounce(() => webshop.checkout_address.takeOver(), 250),
	).observe(host, { childList: true, subtree: true });
});
