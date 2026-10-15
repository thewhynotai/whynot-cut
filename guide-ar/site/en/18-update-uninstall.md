---
title: Updating and uninstalling
slug: 18-update-uninstall
order: 18
lang: en
dir: ltr
---

# Updating and uninstalling {#ch18-title}

This chapter explains how to update WhyNot Cut to a newer version, how to remove it from the computer, and what happens to your clients' files in both cases.

> **Tip:** Today (before version 3.0): updating and removing are in the section [“Today: updating and removing”](#ch18-today), then [“After every update”](#ch18-after-update). The rest of this chapter describes version 3.0.

## Today: updating and removing {#ch18-today}

**To update**: our team sends you the new `whynot-cut-marketplace` folder.

1. Quit the Claude app completely ([Chapter 2](02-install.md#ch02-claude-first)).
2. Delete the old `whynot-cut-marketplace` folder from Documents, and put the new one in its place with the same name. Don't keep both copies.
3. Open Claude, and in a new chat type the first of the two lines below then press Enter, and after it replies type the second line then press Enter. The first reads the new copy of the folder, and the second updates WhyNot Cut to it:

   > **In 3.0 — not verified yet:** These update steps are being reviewed on a real computer, and the two lines may change slightly.
   >
   > ```
   > /plugin marketplace update thewhynot-ai
   > ```
   >
   > ```
   > /plugin update whynot-cut@thewhynot-ai
   > ```
4. Quit Claude completely and open it, and in a new chat type the following command, which updates the engine and the Premiere panel:

   ```
   /whynot-cut:setup
   ```

- **Plans you approved before updating to version 3.0**: Claude asks you to approve them again before the next build. The plan itself doesn't change.
- **To remove it**: ask our team for the steps, because they depend on how the version you have was installed.

## After every update {#ch18-after-update}

1. Quit the Claude app completely ([Chapter 2](02-install.md#ch02-claude-first)) and open it again. A chat that started before the update may still use the old version.
2. Write to Claude “إيه رقم نسخة WhyNot Cut؟” (“What version of WhyNot Cut do I have?”), and it runs the check and tells you the number. Make sure it's the new version number our team told you. If it gives an old number, see [Chapter 17](17-troubleshooting.md#ch17-title).
3. If the Premiere panel changed, quit Premiere Pro and open it again, because it only looks for panels when it opens.

![After the update: Claude gives the new version number.](shots/18-update-uninstall-1.png)

*After the update: Claude gives the new version number.*

## Updating in version 3.0 {#ch18-update}

- **To update all of WhyNot Cut** (the plugin in the Claude app, the engine, the panels and the models), install it again the same way: paste the same install line into Terminal on a Mac or into PowerShell on Windows, or write in Claude “ثبّت WhyNot Cut” (“Install WhyNot Cut”). Running the install a second time updates what changed and repairs what broke, keeps the engine's location, your models and your preferences, and doesn't touch your clients' files ([Chapter 2](02-install.md#ch02-one-line)).
- **On The Why Not AI team's internal computers**: open the newest copy of the WhyNot Cut Setup program ([Chapter 2](02-install.md#ch02-setup-app)).
- **Before you paste the line**, save your work and close Premiere Pro and After Effects, as in [Chapter 2](02-install.md#ch02-one-line). **If one of them is open**, the new panel waits until that program closes, then installs by itself. Meanwhile the old panel shows a card asking you to restart Premiere ([Chapter 17](17-troubleshooting.md#ch17-v3)).
- **If the WhyNot Cut plugin in Claude is older than the rest of WhyNot Cut**, the Claude badge (the small indicator in the panel that shows Claude's status) shows an update button (Update). Click it, then open a new chat.

> **In 3.0 — not verified yet:** The “Update available” message in Claude and going back to the previous version will be explained here when they're released.

## Uninstalling in version 3.0 {#ch18-uninstall}

1. Close Premiere Pro and After Effects. If one of them is open, its panels aren't removed, because an open program blocks deleting its panels' files while it runs; so close it and run the uninstall again.
2. **If you installed with the one line or from inside Claude**: open Terminal on a Mac or PowerShell on Windows as in [“Running a command Claude gave you”](02-install.md#ch02-run-command), paste the removal line for your computer, then press Enter.

   On a Mac, in Terminal:

   ```
   curl -fsSL https://dl.thewhynot.ai/install.sh | bash -s -- --uninstall
   ```

   On Windows, in PowerShell:

   ```
   & ([scriptblock]::Create((irm https://dl.thewhynot.ai/install.ps1))) -Uninstall
   ```
3. **On The Why Not AI team's internal computers** (the WhyNot Cut Setup program): on a Mac open the WhyNot Cut Setup app and uninstall from it. On Windows open Settings › Apps, find WhyNot Cut in the list of apps, then click Uninstall.
4. At the end of the removal it shows you a summary of what was removed and what remains.

![The removal summary: what was removed and what remains on your computer.](shots/18-update-uninstall-2.png)

*The removal summary: what was removed and what remains on your computer.*

What is removed:

- The WhyNot Cut plugin from the Claude app.
- The WhyNot Cut panels from Premiere Pro and After Effects.
- Only the fonts WhyNot Cut installed. Any font that was on your computer before it stays.

What stays unless you ask for it to be deleted:

- The engine folder, so any later install can use it.
- The downloaded models, which stay even if you delete the engine folder, unless you ask for them to be deleted too.

To delete both with the removal, use the full removal line like this. On a Mac, in Terminal:

```
curl -fsSL https://dl.thewhynot.ai/install.sh | bash -s -- --uninstall --remove-engine --remove-models
```

And on Windows, in PowerShell:

```
& ([scriptblock]::Create((irm https://dl.thewhynot.ai/install.ps1))) -Uninstall -RemoveEngine -RemoveModels
```

At the end of the line there are two words: the first (on a Mac `--remove-engine`, on Windows `-RemoveEngine`) deletes the engine folder, and the second deletes the models. Remove either one, together with the space before it, if you want to keep what it deletes.

What always stays:

- Motion and graphics assets with a licence that you added yourself, in the `library` folder inside the engine folder, if there are any.
- Your preferences file, so any later install uses it as it is.
- The clients folder and all the client folders (next section).

> **In 3.0 — not verified yet:** The two removal lines work from the day version 3.0 is released, and haven't been tried on a real computer yet.

## Your clients' files when updating and uninstalling {#ch18-client-files}

While it works, WhyNot Cut never changes what's in the `assets/` and `data/` folders of any client: it doesn't write in them, move anything out of them, or delete anything.

Updating and uninstalling don't move or delete any client folder or any file in it, including the `output/` results folder. The only thing the install or the start wizard may add is a small settings file inside the clients folder and in each client folder, which lets the Claude app work there without asking permission; it doesn't touch your files.

> **In 3.0 — not verified yet:** Protecting client folders when updating and removing will be tried on a real computer before version 3.0 is released.
