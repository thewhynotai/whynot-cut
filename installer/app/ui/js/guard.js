/* The first script of the page: a classic script, so it runs before the HTML below it is parsed and before any module.
   It counts what the strict CSP blocked (securitypolicyviolation) and every uncaught error, for the page self-check
   (selfcheck.js: csp= and jserr=). It changes nothing on the page. */
(function () {
  "use strict";
  var guard = { csp: [], errors: [] };
  Object.defineProperty(window, "__wncGuard", { value: guard });
  document.addEventListener("securitypolicyviolation", function (e) {
    guard.csp.push(String(e.effectiveDirective || e.violatedDirective) + " " + String(e.blockedURI || ""));
  });
  window.addEventListener("error", function (e) { guard.errors.push(String(e.message || "error")); });
  window.addEventListener("unhandledrejection", function (e) { guard.errors.push("unhandled: " + String(e.reason)); });
})();
