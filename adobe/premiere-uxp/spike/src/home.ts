// Home-folder resolution inside UXP. UXP ships a Node-like `os` module (os.homedir()); if it is missing or
// returns nothing we fall back to process.env. Which one worked is recorded in the results (`home_via`).

export interface HomeSources {
  osHomedir?: () => string;
  env?: Record<string, string | undefined>;
}

export interface HomeResult {
  home: string | null;
  via: "os.homedir" | "env.USERPROFILE" | "env.HOME" | "env.HOMEDRIVE+HOMEPATH" | "none";
}

export function toForwardSlashes(p: string): string {
  return p.replace(/\\/g, "/");
}

function clean(p: string | undefined | null): string | null {
  if (!p) return null;
  const s = toForwardSlashes(p.trim()).replace(/\/+$/, "");
  return s.length > 0 ? s : null;
}

export function resolveHome(src: HomeSources): HomeResult {
  if (src.osHomedir) {
    try {
      const h = clean(src.osHomedir());
      if (h) return { home: h, via: "os.homedir" };
    } catch {
      // fall through to env
    }
  }
  const env = src.env ?? {};
  const profile = clean(env.USERPROFILE);
  if (profile) return { home: profile, via: "env.USERPROFILE" };
  const home = clean(env.HOME);
  if (home) return { home, via: "env.HOME" };
  if (env.HOMEDRIVE && env.HOMEPATH) {
    const h = clean(env.HOMEDRIVE + env.HOMEPATH);
    if (h) return { home: h, via: "env.HOMEDRIVE+HOMEPATH" };
  }
  return { home: null, via: "none" };
}

/** `<home>/.whynot-cut/uxp-spike` - config.json is read from here, results-<ts>.json are written here. */
export function spikeDir(home: string): string {
  return `${home.replace(/\/+$/, "")}/.whynot-cut/uxp-spike`;
}
