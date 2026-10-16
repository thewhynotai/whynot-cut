/* Test fixture (never part of ui/): mounts a first view (with a missing key) and returns a second one, which main.js
   mounts at once. Only the second view's self-check may be in the page, and its missing list must be empty. */
export default function ({ demo, I, mount }) {
  const first = demo.shellView({});
  first.state = "first";
  first.body.append(I.T("no.such.key.first"));
  mount(first);
  return demo.shellView({});
}
