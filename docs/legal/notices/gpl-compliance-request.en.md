# GPL compliance request (template, English)

> **Not legal advice. Have a lawyer review this text before you send it.** This is a fill-in template: replace every
> double-brace field and delete what does not apply.

## Before sending (delete this section from the letter)
- [ ] The release you cite contains our `LICENSE` file and the SPDX licence and copyright headers (task BL-02 is
      merged and released). Do not send this letter before that.
- [ ] Every double-brace field is filled, and what does not apply is deleted.
- [ ] A lawyer has read the final text.

{{date}}

To: {{recipient}}
From: {{sender_org}} ({{contact}})

**Subject: Request for GPL compliance for {{their_product}}**

Dear {{recipient}},

{{sender_org}} publishes WhyNot Cut at {{our_repo}} under the GNU General Public License, version 3 or (at your
option) any later version. Our source files carry SPDX licence and copyright notices.

We believe that {{their_product}}, distributed at {{their_location}}, contains or is derived from our code. The
evidence we hold is listed under "Attachments" below.

The GNU General Public License lets anyone copy, change and distribute the code, on the condition that every
recipient also gets:
- the full licence text;
- our copyright and licence notices, kept intact;
- the complete corresponding source code of the distributed work, under the same licence;
- a clear statement of what you changed and when.

We ask you to do one of the following within {{deadline_days}} days of the date of this letter:
1. make the complete corresponding source code of {{their_product}} available to every recipient, as the licence
   requires (for example by publishing it), under the same licence and with the notices restored, and tell us how;
   or
2. stop distributing {{their_product}} and tell us in writing that you have stopped.

If you think we are mistaken, please send us your reasoning and the origin of the code in question. We would be glad
to resolve this directly and in good faith. This letter does not waive any of our rights.

Please answer to {{contact}}.

Kind regards,
{{sender_org}}

## Attachments (what to attach before sending)
1. **Commit history**: the log of our repository for the files concerned (commit ids, dates, authors as they appear
   in git), showing that our code existed first. Export it with `git log --follow` for each file and attach the output.
2. **Release hashes**: the SHA-256 hash of each of our release archives that contains the code, so that anyone can
   check the files against our public release.
3. **Tag names**: the exact tag names of the releases concerned (for example the release tag, copied as it appears
   in the repository).
4. **Side-by-side evidence**: {{evidence}} (file names, screenshots or diffs that show the match).
5. **Their distribution**: the date and the place where you obtained {{their_product}}.
