/* Currency and timezone choices for restaurant forms. */
export const CURRENCY_SUGGESTIONS = ["USD", "EUR", "GBP", "NGN", "GHS", "KES", "ZAR", "CAD", "AUD", "INR"];

export function defaultTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function timezoneOptions(selected) {
  let zones = [];
  try {
    zones = Intl.supportedValuesOf("timeZone");
  } catch {
    /* older browser: fall back to the few below */
  }
  const set = new Set(["UTC", ...zones, ...(selected ? [selected] : [])]);
  return [...set].sort().map((zone) => ({ value: zone, label: zone }));
}

/** Fields shared by "create restaurant" and "edit details". */
export function restaurantFields({ includeSlug = false, timezone } = {}) {
  const fields = [{ name: "name", label: "Restaurant name", type: "text", required: true, maxlength: 120, autocomplete: "organization" }];
  if (includeSlug) fields.push({ name: "slug", label: "Web address", type: "text", required: true, maxlength: 63, hint: "" });
  fields.push(
    { name: "description", label: "About (optional)", type: "textarea", maxlength: 1000 },
    { name: "address", label: "Address (optional)", type: "text", maxlength: 255, autocomplete: "street-address" },
    { name: "contact_phone", label: "Phone (optional)", type: "tel", inputmode: "tel", maxlength: 32, autocomplete: "tel" },
    {
      name: "currency", label: "Currency", type: "text", required: true, maxlength: 3, suggestions: CURRENCY_SUGGESTIONS,
      hint: "A 3-letter code, e.g. USD.",
      validate: (v) => (/^[A-Za-z]{3}$/.test(v) ? null : "Use a 3-letter code such as USD."),
    },
    { name: "timezone", label: "Timezone", type: "select", required: true, options: timezoneOptions(timezone) },
    { name: "pickup_enabled", label: "Customers can order for pickup", type: "checkbox" },
    { name: "dine_in_enabled", label: "Customers can order to eat in", type: "checkbox" },
    { name: "requires_table_number", label: "Ask dine-in customers for a table number", type: "checkbox" },
  );
  return fields;
}

export function fulfilmentErrors(values) {
  const errors = {};
  if (!values.pickup_enabled && !values.dine_in_enabled) errors.pickup_enabled = "Choose at least one way for customers to order.";
  if (values.requires_table_number && !values.dine_in_enabled) errors.requires_table_number = "Table numbers only apply to dine-in.";
  return errors;
}
