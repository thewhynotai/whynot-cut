/* Test fixture (never part of ui/): asks for a key and an icon that do not exist; the self-check must list both. */
export default function ({ demo, I }) {
  const view = demo.shellView({});
  view.body.appendChild(I.T("no.such.key"));
  view.body.appendChild(I.ico("no-such-icon", 16));
  return view;
}
