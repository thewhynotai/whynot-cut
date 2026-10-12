// The WhyNot Cut UXP plugin ids and the release name, with no imports, so dev-install.mjs can use them without loading
// package-ccx.mjs (and through it build.mjs and esbuild). package-ccx.mjs keeps its own RELEASE_ID; a test checks the
// two are equal.
export const RELEASE_ID = "ai.thewhynot.cut";
/** The release plugin's name, as UPIA `/list all` and Window > UXP Plugins show it (C4/H5). */
export const RELEASE_NAME = "WhyNot Cut";
export const DEV_ID = "ai.thewhynot.cut.dev";
export const SPIKE_ID = "ai.thewhynot.cut.spike";
