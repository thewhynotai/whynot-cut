/* Test fixture (never part of ui/): sets a style attribute, which style-src 'self' blocks. The page's own CSP counter
   and the browser console must both report it, or the "zero violations" test proves nothing. */
export default function ({ demo }) {
  const view = demo.shellView({});
  const probe = document.createElement("div");
  probe.setAttribute("style", "color: red");
  view.body.appendChild(probe);
  return view;
}
