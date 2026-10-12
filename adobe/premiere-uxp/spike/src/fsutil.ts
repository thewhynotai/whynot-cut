// Thin async helpers over UXP's `fs`: use the promise API when present, else the *Sync twin, else say so.
import { toForwardSlashes } from "./home.ts";
import type { UxpFs, UxpStats } from "../../src/uxp-types.ts";

async function fsCall<T>(fs: UxpFs, name: string, ...args: unknown[]): Promise<T> {
  const plain = fs[name];
  if (typeof plain === "function") return (await (plain as (...a: unknown[]) => unknown).apply(fs, args)) as T;
  const sync = fs[`${name}Sync`];
  if (typeof sync === "function") return (sync as (...a: unknown[]) => unknown).apply(fs, args) as T;
  throw new Error(`fs.${name} is not available in this UXP runtime`);
}

export async function readText(fs: UxpFs, path: string): Promise<string> {
  const data = await fsCall<string | ArrayBuffer>(fs, "readFile", path, { encoding: "utf-8" });
  return typeof data === "string" ? data : new TextDecoder().decode(data);
}

/** Binary read: no encoding, so UXP answers an ArrayBuffer (a Node Buffer in tests). */
export async function readBytes(fs: UxpFs, path: string): Promise<ArrayBuffer> {
  const data = await fsCall<ArrayBuffer | ArrayBufferView | string>(fs, "readFile", path);
  if (typeof data === "string") throw new Error("fs.readFile without an encoding returned text, not bytes");
  if (data instanceof ArrayBuffer) return data;
  const v = data as ArrayBufferView;
  return v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) as ArrayBuffer;
}

export async function writeBytes(fs: UxpFs, path: string, data: ArrayBuffer): Promise<void> {
  await fsCall(fs, "writeFile", path, data);
}

export async function writeText(fs: UxpFs, path: string, text: string): Promise<void> {
  await fsCall(fs, "writeFile", path, text, { encoding: "utf-8" });
}

export async function statOf(fs: UxpFs, path: string): Promise<{ exists: boolean; bytes: number | null; isDir: boolean | null }> {
  try {
    const st = await fsCall<UxpStats>(fs, "lstat", path);
    return { exists: true, bytes: typeof st.size === "number" ? st.size : null, isDir: typeof st.isDirectory === "function" ? st.isDirectory() : null };
  } catch {
    return { exists: false, bytes: null, isDir: null };
  }
}

/** mkdir -p, segment by segment (UXP's mkdir has no guaranteed `recursive`). */
export async function ensureDir(fs: UxpFs, dir: string): Promise<void> {
  const parts = toForwardSlashes(dir).split("/");
  let acc = "";
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i] ?? "";
    acc = i === 0 ? part : `${acc}/${part}`;
    if (acc === "" || /^[A-Za-z]:$/.test(acc)) continue;
    if ((await statOf(fs, acc)).exists) continue;
    try {
      await fsCall(fs, "mkdir", acc);
    } catch (err) {
      if (!(await statOf(fs, acc)).exists) throw err;
    }
  }
}

export function baseName(path: string): string {
  const p = toForwardSlashes(path);
  return p.slice(p.lastIndexOf("/") + 1);
}
