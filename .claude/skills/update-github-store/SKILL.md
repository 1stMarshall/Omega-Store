---
name: update-github-store
description: Sync the public GitHub Pages copy of the Omega Trade Route store (1stMarshall/Omega-Store, https://1stmarshall.github.io/Omega-Store/) with the live Claude store artifact, then push to main. Use when the user says "update the github store", "sync the store to GitHub", "push the store", or asks to make GitHub match the live/Claude store.
---

# Update the GitHub store

The live Claude store is the source of truth:
https://claude.ai/artifact/K2YrQZMpnQbk7wZMuwLepm

The GitHub copy is `index.html` in this repo. Its store data is the JSON inside
`<script type="application/json" id="otr-data">`. Product photos are not embedded:
each one is a file `images/<first 12 hex chars of SHA-1 of the bytes>.jpg`, and the
product's `img` (and the store `logo`) holds that path.

## Rules

- Copy store data only: products (new, removed, and changed name, price, category, note, options, status, photo, variant fields), store text, batch, contact and `nextId`.
- Keep GitHub's own `store.storeLink`. Never copy it from the live store.
- Copy customer order tracking (`track`, `trackAt`, `trackSalt`, `trackSig`) from the live store. The owner publishes tracking there with **Publish order updates**; without this step customers on GitHub can't find new orders.
- Never change the page code, `<head>` tags, icons, `share.jpg` or `.nojekyll`. Never edit, recompress or resize photos. Decode them byte for byte.
- Push straight to `main`. Don't leave the work on another branch, and don't open a PR unless asked.

## Steps

Run the commands from the repo root. `$K` is `.claude/skills/update-github-store/scripts`, and `$S` is your scratchpad directory.

1. **Read the current live store.** Call the Artifact tool with `action: "read"` and the URL above, on every run. Never reuse a copy from earlier in the conversation. The result names the file that holds the full page, under `tool-results/artifact-...html`. Note that path and the version id.

2. **Start from the latest main.**
   ```
   git checkout main && git fetch origin main && git merge --ff-only origin/main
   ```
   Stop and tell the user if the working tree isn't clean or the fast-forward fails.

3. **Compare (dry run).**
   ```
   python3 -I $K/sync_store.py <live file> --expect-out $S/expect.json
   ```
   It prints every ADDED, CHANGED and REMOVED product, each FIELD change, and each NEW FILE photo.
   - `NO DIFFERENCES` means GitHub already matches. Tell the user and stop; there's nothing to commit.
   - A `PROBLEM` line makes the script exit with status 1. Show it to the user. In particular, "page code differs" means the live page's HTML/CSS/JS changed. This skill doesn't copy that, so ask the user before doing anything about it. Store data can still be synced.
   - "Kept GitHub values for: store.storeLink" is expected, not a problem.
   - A `TRACKING` line means customer order tracking changed. It counts as a difference on its own, so sync even when no product changed.

4. **Apply.** Run the same command with `--write` added. Then confirm that `git status` shows only `index.html` and new `images/*` files, and that `git diff -U0 index.html | grep '^@@'` shows a single changed line (the data line).

5. **Check in a headless browser.**
   ```
   node $K/check_page.js . $S/expect.json $S
   ```
   It serves the repo locally, loads `index.html`, and checks four things: no script errors, no failed requests, every added or changed product has a card with a loaded photo, and every image the data references exists. A variant (`variantOf`) shows inside its group's card, and the script checks that card instead. Exit 0 means pass. On failure, fix the cause or restore with `git checkout -- index.html && git clean -fd images`. Never commit a failing state. Look at one or two of the `product-<id>.png` screenshots it saves.

6. **Commit and push to main.**
   ```
   git add index.html images/
   git commit -m "Add/update products #A-#B from live store" -m "<one line per product>"
   git push origin main
   git fetch origin main && git log --oneline -1 origin/main
   ```
   Use the session's commit attribution trailer if one is configured. Confirm that `origin/main` now points at your commit.

7. **Report to the user.**
   - Every product added, changed or removed, as #number, name, category and price. For a change, say what changed (old → new).
   - Any store, batch or contact text changes, and the old → new `nextId`.
   - That `storeLink` was kept, and whether customer order tracking was updated (record count and publish time from the `TRACKING` line).
   - The browser check result.
   - The commit hash on `main`, and that GitHub Pages takes a minute or two to update.

   If the user expected products that already were on GitHub, say so plainly.
