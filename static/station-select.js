// Submit the station-picker form as soon as a station is chosen. External
// file: inline `onchange="..."` handlers are blocked by the app's
// `script-src 'self'` CSP (no 'unsafe-inline').
document.querySelectorAll("select[data-autosubmit]").forEach((select) => {
  select.addEventListener("change", () => select.form.submit());
});
