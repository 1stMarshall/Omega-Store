// Headless check of the GitHub copy of the store.
// Usage: node check_page.js REPO_DIR EXPECT_JSON [SCREENSHOT_DIR] [--placeholder-missing]
// EXPECT_JSON comes from sync_store.py --expect-out. Exits 1 on any failure.
// --placeholder-missing (chat mode): photos not in REPO_DIR are already on GitHub,
// so they are served as a 1x1 placeholder instead of failing.
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const placeholder = process.argv.includes('--placeholder-missing');
const [repo, expectFile, shotDir] = process.argv.slice(2).filter(a => a !== '--placeholder-missing');
const PIXEL = Buffer.from('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==', 'base64');
const served = new Set();
const { expect, imgs } = JSON.parse(fs.readFileSync(expectFile, 'utf8'));
const TYPES = { '.html': 'text/html; charset=utf-8', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif' };

const root = path.resolve(repo);
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  const rel = path.relative(root, p).split(path.sep).join('/');
  if (placeholder && rel.startsWith('images/') && !fs.existsSync(p)) { served.add(rel); res.writeHead(200, { 'Content-Type': 'image/jpeg' }); return res.end(PIXEL); }
  if (!p.startsWith(root) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(p)] || 'application/octet-stream' });
  fs.createReadStream(p).pipe(res);
});

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + server.address().port + '/';
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [], failed = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('response', r => { if (r.url().startsWith(base) && r.status() >= 400) failed.push(r.status() + ' ' + r.url()); });
  await page.goto(base + 'index.html', { waitUntil: 'networkidle' });

  let bad = 0;
  console.log('cards rendered:', await page.locator('.card').count());
  for (const e of expect) {
    if (e.status === 'hidden') { console.log('skip (hidden) #' + e.id + ' ' + e.name); continue; }
    const card = page.locator('.card').filter({ has: page.locator('h3', { hasText: e.card }) }).first();
    if (!(await card.count())) { bad++; console.log('MISSING card for #' + e.id + ' ' + e.name + (e.card !== e.name ? ' (group: ' + e.card + ')' : '')); continue; }
    await card.scrollIntoViewIfNeeded();
    const img = card.locator('.card-media img');
    let ok = 'no photo';
    if (await img.count()) {
      await page.waitForFunction(el => el.complete && el.naturalWidth > 0, await img.first().elementHandle(), { timeout: 10000 }).catch(() => {});
      ok = (await img.first().evaluate(i => i.complete && i.naturalWidth > 0)) ? 'photo ok' : 'PHOTO NOT LOADED';
      if (ok !== 'photo ok') bad++;
      else if (served.has(e.img)) ok = 'photo already on GitHub (placeholder used)';
    }
    console.log('#' + e.id + ' ' + e.name + (e.card !== e.name ? ' (in group: ' + e.card + ')' : '') + ': ' + ok + ' | ' + (await card.innerText()).replace(/\n+/g, ' | ').slice(0, 120));
    if (shotDir) await card.screenshot({ path: path.join(shotDir, 'product-' + e.id + '.png') });
  }
  // every image the data references must be served
  const missing = await page.evaluate(async list => {
    const out = [];
    for (const u of list) { const r = await fetch(u); if (!r.ok || !(r.headers.get('content-type') || '').startsWith('image/')) out.push(u + ' ' + r.status); }
    return out;
  }, imgs);
  console.log('image files referenced:', imgs.length, 'missing:', missing.length ? missing : 'none', placeholder ? '(chat mode: photos already on GitHub are placeholders)' : '');
  console.log('script errors:', errors.length ? errors : 'none');
  console.log('failed requests:', failed.length ? failed : 'none');
  await browser.close(); server.close();
  process.exit(bad || missing.length || errors.length || failed.length ? 1 : 0);
})().catch(e => { console.error(e); server.close(); process.exit(1); });
