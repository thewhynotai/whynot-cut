---
title: Cost and data
slug: data
lang: en
dir: ltr
status: draft — Yunus publishes (H24)
links: rewrite ../{ar,en}/… to the live guide URLs at publish; if the guide isn't live, make them plain text
---

# Cost and data

This page says what WhyNot Cut needs from Claude, what is sent and to whom, what is never sent, and how long it is kept. It is not a privacy policy: for the legal details, see Anthropic's privacy pages.

## Cost

Each editor needs their own Claude Pro or Max plan, paid to Anthropic (Pro from $20 a month; prices vary by country). WhyNot Cut adds nothing on top.

- WhyNot Cut works through Claude Code, which is part of the Pro and Max plans and uses the same usage limits as the plan.
- See plans: [the Pro plan](https://support.claude.com/en/articles/8325606-what-is-the-pro-plan) and [the Max plan](https://support.claude.com/en/articles/11049741-what-is-the-max-plan) (Anthropic's pages).
- Magnific is optional: you use it with your own account there, it has its own credits, and WhyNot Cut works fully without it.

## What is sent, and to whom

Video and audio files are never uploaded. Claude reads text (the transcript and the plan) and a few still images: some timeline frames for checking, and brand photos.

- **To Anthropic (Claude):** Claude runs on the editor's own Claude account. Besides the transcript and the plan, it reads the client's brief and notes. With Kalam in version 3.0, only the caption text reaches Claude.
- **To Magnific:** if you use it, it receives from your own account only the images you ask it to process, such as the client's logo.
- **To WhyNot Cut:** nothing. No telemetry: WhyNot Cut sends no usage data anywhere.

## What is never sent

- The video and audio files themselves.
- The client folder: it stays on your computer, or on the drive you chose. The transcript is made on your computer.
- WhyNot Cut trains on nothing: your footage and edits never train any model.

## How long Anthropic keeps data

What Claude reads is handled under your Claude plan's terms. For client work, turn off 'Help improve our AI models' in Claude's privacy settings. Medical clients: use a Team or Enterprise plan, where data isn't used for training.

| Plan | How long it is kept |
|---|---|
| Free, Pro or Max, with "Help improve our AI models" off | 30 days |
| Free, Pro or Max, with "Help improve our AI models" on | up to 5 years, de-identified, for training |
| Team or Enterprise | not used for training; kept 30 days |

These details and numbers come from Anthropic's pages and can change, so check them there: [How long do you store my data?](https://privacy.claude.com/en/articles/10023548-how-long-do-you-store-my-data) and [Data usage in Claude Code](https://code.claude.com/docs/en/data-usage).

## The right plan for each client

- **Most clients:** Pro or Max, with "Help improve our AI models" off.
- **Medical clients:** Team or Enterprise.

## How to remove data

- **On your computer:** the client folders are yours, and deleting them is up to you. Uninstalling WhyNot Cut never touches your client files.
- **In the Claude app on your computer:** your chats keep a copy of what Claude read, such as the transcript and the plan. Chats in the Claude desktop app are not deleted automatically: they stay on your computer until you delete them. Delete a client's chats when you no longer need them. Anthropic's page explains how, for one project folder or for all of them at once: [Clear local data](https://code.claude.com/docs/en/claude-directory#clear-local-data).
- **At Anthropic:** when you delete a conversation in Claude, it leaves your history right away and is deleted from Anthropic's systems within 30 days. If you turn off "Help improve our AI models", your data stays out of new training, but data already used in training stays there. The details are in Anthropic's privacy pages.
- **At Magnific:** this follows your account there. See Magnific's own pages.

For more on where your clients' data stays, see [Where your clients' data stays](../en/01-intro.md#ch01-data) in the guide.
