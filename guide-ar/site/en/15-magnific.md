---
title: Magnific assets
slug: 15-magnific
order: 15
lang: en
dir: ltr
---

# Magnific assets {#ch15-title}

Magnific is a separate service for processing images and generating visual assets, such as enlarging a small image at higher quality (upscale), turning a logo into a vector drawing, removing a background, and generating icons and backgrounds. You use it with your own account there, it has its own credits separate from WhyNot Cut, and WhyNot Cut works fully without it.

> **Tip:** Today the work doesn't need Magnific: WhyNot Cut works with the client's files alone ([Chapter 4](04-client-folder.md#ch04-title)). The rest of this chapter describes the Magnific link in version 3.0.

> **In 3.0 — not verified yet:** The Magnific link isn't in the version you have today, and its details may change before release.

## When Magnific assets are used {#ch15-when}

The rules:

- They are used only to fill a specific gap in the plan, tied to a moment in what the speaker says, and only after first searching the client's own files.
- The uses: improving a low-quality logo, turning it into a vector drawing, cutting out the background, icons, backgrounds, and illustrations in place of supporting footage (B-roll).
- Never generated: real faces or people, footage of real events, or any asset that presents a fact or a claim.
- In medical and religious videos every asset is reviewed before it's placed, like a graphic that carries a medical fact.

> **In 3.0 — not verified yet:** These rules come from the Magnific link's spec, and haven't been tried yet.

## Approval and budget {#ch15-approval}

- No credits are spent automatically.
- For each reel you give one approval of the list of assets needed, with each asset's estimated cost, within a budget you set in the preferences ([Chapter 16](16-preferences.md#ch16-list)).
- Any request outside what you approved, or over the budget, stops and asks you first.

> **In 3.0 — not verified yet:** Approving assets and the budget limit haven't been tried yet.

## The Magnific asset record {#ch15-license}

Every asset from Magnific is recorded in the file `magnific-manifest.json` (a data file the program reads; you don't need to open it) inside the `output/` results folder, together with: where it came from, which tool made it, when, how much it cost, and that its files aren't delivered to the client.

> **In 3.0 — not verified yet:** The record file's name and layout may change slightly before release.

## What isn't delivered to the client from Magnific assets {#ch15-not-delivered}

Magnific assets are never placed inside the editable files delivered to the client, and the handoff file lists them as Magnific assets whose files aren't delivered to the client, used under your Magnific account's terms. The final exported video can contain them.

> **In 3.0 — not verified yet:** This rule comes from the Magnific link's spec, and hasn't been tried in a real handoff file yet.

## Working without Magnific {#ch15-absent}

Not having Magnific never stops the work: WhyNot Cut carries on with the client's files and tells you which asset is missing.

> **In 3.0 — not verified yet:** Turning on Magnific is an optional step explained in [Chapter 2](02-install.md#ch02-title) when it's released.
