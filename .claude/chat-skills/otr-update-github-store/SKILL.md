---
name: otr-update-github-store
description: In a claude.ai chat, prepare an update of the public GitHub Pages copy of the Omega Trade Route store (1stMarshall/Omega-Store) so it matches the live Claude store. Builds the new index.html and only the new photos as downloads, with step-by-step instructions for the owner to upload them on github.com. Use when the owner says "update the github store", "sync the store to GitHub" or similar in chat. In a Claude Code session that has the Omega-Store repo checked out, use the repo's update-github-store skill instead, because it can push directly.
---

# Update the GitHub store (from chat)

Chat can't push to GitHub. This skill builds the exact files to upload, checks them, and tells the owner how to upload them on github.com.

- Live store (source of truth): https://claude.ai/artifact/K2YrQZMpnQbk7wZMuwLepm
- GitHub copy: https://github.com/1stMarshall/Omega-Store, served at https://1stmarshall.github.io/Omega-Store/
- In the GitHub copy, the store data is the JSON in `<script type="application/json" id="otr-data">` in `index.html`. Photos are files `images/<first 12 hex chars of SHA-1 of the bytes>.jpg`, and each product's `img` holds that path.

## Rules
- Copy store data only: products (new, removed, and changed name, price, category, note, options, status, photo, variant fields), store text, batch, contact and `nextId`.
- Keep GitHub's own `store.storeLink`. Never take it from the live store.
- Copy customer order tracking (`track`, `trackAt`, `trackSalt`, `trackSig`) from the live store. The owner publishes tracking there with **Publish order updates**; without this step customers on GitHub can't find new orders.
- Never change page code, `<head>` tags, icons or `share.jpg`. Never edit, crop or recompress photos. They are decoded byte for byte.
- Never edit the live store in this skill. It only reads it.

## Steps
Work in `/tmp/otr-sync`. The scripts are in this skill's `scripts/` folder. Find them with
`find / -name sync_store.py -path '*otr-update-github-store*' 2>/dev/null`, and call that folder `$K`.

1. **Read the live store now.** Use `Artifact` action `read` with the store URL. Do this on every run and never reuse an earlier copy. Note the saved HTML path it reports and the version id.

2. **Get the current GitHub index.html.** Try these in order:
   ```
   curl -sfL https://raw.githubusercontent.com/1stMarshall/Omega-Store/main/index.html -o /tmp/otr-sync/github-index.html
   curl -sfL https://1stmarshall.github.io/Omega-Store/index.html -o /tmp/otr-sync/github-index.html
   ```
   If both fail, ask the owner to open https://github.com/1stMarshall/Omega-Store/blob/main/index.html, tap **Download raw file**, and attach it here. Then use the file from `/mnt/user-data/uploads`.
   Sanity check: the file must contain the `otr-data` block, and its `store.storeLink` must be `https://1stmarshall.github.io/Omega-Store/`. raw.githubusercontent.com can be up to about 5 minutes behind a fresh upload. If the owner has just uploaded, wait or use the github.io URL.

3. **Compare and build.**
   ```
   cd /tmp/otr-sync && python3 -I $K/sync_store.py <live html> --github-index github-index.html \
       --out /mnt/user-data/outputs/omega-store-update --expect-out expect.json
   ```
   - The output lists every ADDED, CHANGED and REMOVED product, each FIELD change, and each NEW FILE photo.
   - `NO DIFFERENCES` means GitHub already matches. Tell the owner and stop. Nothing needs uploading.
   - A `PROBLEM` line makes the script exit with status 1. Tell the owner. "Page code differs" means the live page's design or code changed. This skill doesn't copy that, so ask before doing anything about it.
   - "Kept GitHub values for: store.storeLink" is expected.
   - A `TRACKING` line means customer order tracking changed. It counts as a difference on its own, so build the update even when no product changed.
   - The output folder gets `index.html` plus an `images/` folder that holds only photos GitHub doesn't have yet.

4. **Check in a headless browser.**
   ```
   NODE_PATH=$(npm root -g) node $K/check_page.js /mnt/user-data/outputs/omega-store-update expect.json /tmp/otr-sync --placeholder-missing
   ```
   - It must exit 0, with no script errors, a card with a loaded photo for every added or changed product, and no missing image files.
   - Photos already on GitHub are stood in by a placeholder; that's expected.
   - Look at one or two of the saved `product-<id>.png` screenshots.
   - If it fails, don't hand over the files. Fix the cause, or tell the owner.

5. **Package.** Zip the folder so the owner can download it in one go:
   ```
   cd /mnt/user-data/outputs && zip -r omega-store-update.zip omega-store-update
   ```
   Keep the unzipped folder too, so the files can also be downloaded one by one on a phone.

6. **Reply to the owner.**
   - What changed: every product added, changed or removed (#number, name, category, price; for a change, old → new), any store, batch or contact text changes, and nextId old → new. Say that storeLink was kept, and whether customer order tracking was updated.
   - The files to upload: `index.html`, plus each new photo name.
   - Upload instructions:
     - **On a computer:** go to https://github.com/1stMarshall/Omega-Store and click **Add file → Upload files**. Unzip the download, open the `omega-store-update` folder, and drag both its contents in at once: `index.html` and the `images` folder. Choose **Commit directly to the main branch**, paste the commit message below, and click **Commit changes**.
     - **On a phone (no folder upload):** first go to https://github.com/1stMarshall/Omega-Store/tree/main/images, then **Add file → Upload files**, and pick the new photos. Next go back to https://github.com/1stMarshall/Omega-Store, then **Add file → Upload files**, and pick `index.html`. Commit each upload to main.
     - Give a ready-to-paste commit message, for example `Add products #96-#102 from live store`.
   - Tell the owner to upload soon. If the store or GitHub changes before the upload, these files are out of date, so run this skill again.
   - After the upload, GitHub Pages updates in a minute or two. To confirm, the owner can say "check the github store": run steps 1–3 again and expect `NO DIFFERENCES`.
