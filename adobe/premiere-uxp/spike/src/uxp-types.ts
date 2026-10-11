// Local, minimal UXP typings: only what the spike uses. No maintained UXP typings package covers Premiere
// (@adobe/cc-ext-uxp-types was last published 2023; @adobe-uxp-types/uxp is a third-party hobby package), so these
// stay local and loose on purpose - the spike's job is to find out which of these really exist.

export interface UxpStats {
  size?: number;
  isFile?: () => boolean;
  isDirectory?: () => boolean;
}

/** UXP `require("fs")`. Every member is optional: the spike records which ones are actually present. */
export interface UxpFs {
  readFile?: (path: string, options?: { encoding: string } | string) => Promise<string | ArrayBuffer>;
  writeFile?: (path: string, data: string | ArrayBuffer, options?: { encoding: string } | string) => Promise<unknown>;
  mkdir?: (path: string, options?: { recursive?: boolean }) => Promise<unknown>;
  lstat?: (path: string) => Promise<UxpStats>;
  readdir?: (path: string) => Promise<string[]>;
  readFileSync?: (path: string, options?: { encoding: string } | string) => string | ArrayBuffer;
  writeFileSync?: (path: string, data: string | ArrayBuffer, options?: { encoding: string } | string) => unknown;
  mkdirSync?: (path: string, options?: { recursive?: boolean }) => unknown;
  lstatSync?: (path: string) => UxpStats;
  [name: string]: unknown;
}

export interface UxpOs {
  homedir?: () => string;
  platform?: () => string;
  release?: () => string;
  arch?: () => string;
  [name: string]: unknown;
}

export interface UxpHost {
  name?: string;
  version?: string;
  uiLocale?: string;
  getBackgroundColor?: () => unknown;
  [name: string]: unknown;
}

/** UXP `require("uxp")`. */
export interface UxpModule {
  host?: UxpHost;
  versions?: { uxp?: string; plugin?: string; [name: string]: unknown };
  storage?: { localFileSystem?: Record<string, unknown>; [name: string]: unknown };
  [name: string]: unknown;
}
