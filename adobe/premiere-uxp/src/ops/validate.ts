// Contract checks at the adapter's edge: a command's `data` against the action's $defs/data before Premiere is touched,
// and the op's readback against $defs/readback before it is sent. The checks are ajv standalone code compiled from the
// contract (validators.gen.js, scripts/gen-validators.mjs): no ajv at runtime and no code generated in UXP.
import * as gen from "./validators.gen.js";
import type { GeneratedValidator } from "./validators.gen.js";

const CHECKS = gen as unknown as Record<string, GeneratedValidator | undefined>;

type AjvError = NonNullable<GeneratedValidator["errors"]>[number];

/** One short reason from ajv's first error: where, then what. */
function describe(e: AjvError | undefined): string {
  if (!e) return "it does not match the contract";
  const at = e.instancePath || "/";
  const p = e.params ?? {};
  switch (e.keyword) {
    case "required":
      return `${at}: ${String(p.missingProperty)} is missing`;
    case "additionalProperties":
      return `${at}: ${String(p.additionalProperty)} is not allowed`;
    case "type":
      return `${at}: must be ${Array.isArray(p.type) ? p.type.join(" or ") : String(p.type)}`;
    case "minimum":
    case "maximum":
    case "exclusiveMinimum":
    case "exclusiveMaximum":
      return `${at}: must be ${String(p.comparison)} ${String(p.limit)}`;
    case "minLength":
      return `${at}: must have at least ${String(p.limit)} character(s)`;
    case "minItems":
      return `${at}: must have at least ${String(p.limit)} item(s)`;
    case "enum":
    case "const":
      return `${at}: is not one of the allowed values`;
    default:
      return `${at}: fails ${e.keyword}`;
  }
}

function check(name: string, value: unknown): string | null {
  const fn = CHECKS[name];
  if (typeof fn !== "function") return `there is no check for ${name}`;
  return fn(value) ? null : describe(fn.errors?.[0]);
}

/** null when `data` is valid for the action, else one short reason. */
export function validateData(action: string, data: unknown): string | null {
  return check(`${action}_data`, data);
}

/** null when `readback` is valid for the action, else one short reason. */
export function validateReadback(action: string, readback: unknown): string | null {
  return check(`${action}_readback`, readback);
}
