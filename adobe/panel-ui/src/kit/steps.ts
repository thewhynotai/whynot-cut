// The step strip: Transcript › Plan › Approve › Build › Frames › QC › Handoff (Addendum B4.3). Always the 7 pipeline
// steps in order; a step the source does not send, or an unknown state, is pending. Done and failed dots carry their
// icon; the others a step number (a left-to-right run). Separators are chevrons that point the reading direction, and
// CSS direction lays the strip out right-to-left in Arabic (the DOM order never changes).
import { fmt } from "../i18n.ts";
import type { StringKey, Strings } from "../i18n.ts";
import { STEP_IDS } from "../source.ts";
import type { StepId, StepStatus } from "../source.ts";
import { esc, ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";
import { icon } from "./icons.ts";

const STATES: readonly StepStatus[] = ["done", "running", "waiting", "pending", "failed"];

export interface StepView {
  id: StepId;
  state: StepStatus;
}

export interface StepStripOpts {
  t: Strings;
  steps: readonly StepView[];
  rtl: boolean;
}

export function stepStrip(o: StepStripOpts): Html {
  const byId = new Map<string, StepView>(o.steps.map((s) => [s.id, s]));
  const items = STEP_IDS.map((id, i) => {
    const raw = byId.get(id)?.state;
    const state: StepStatus = raw && STATES.includes(raw) ? raw : "pending";
    const name = o.t[`step.${id}` as StringKey];
    const label = fmt(o.t["step.aria"], { name, state: o.t[`step.state.${state}` as StringKey] });
    const dot = state === "done" ? icon("ok") : state === "failed" ? icon("error") : ltr(i + 1);
    const current = state === "running" || state === "waiting" ? ` aria-current="step"` : "";
    const sep = i < STEP_IDS.length - 1 ? `<span class="kit-step-sep">${icon("chevron-end", { rtl: o.rtl })}</span>` : "";
    return (
      `<li class="kit-step kit-step-${state}" data-step="${id}" aria-label="${esc(label)}"${current}>` +
      `<span class="kit-step-dot">${dot}</span><span class="kit-step-name">${esc(name)}</span>${sep}</li>`
    );
  }).join("");
  return trusted(`<ol class="kit-steps" aria-label="${esc(o.t["section.pipeline"])}">${items}</ol>`);
}
