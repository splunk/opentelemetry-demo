# Do NOT re-add `--ignore-certificate-errors` or `acceptInsecureCerts: true`

## Symptom

Loadgen fails **every cycle from #1** with:

```
⚠️ /api/data did not complete in 15s, continuing anyway...
❌ Cycle #N failed: TimeoutError: Waiting for selector `[data-cy='product-add-to-cart']` failed
```

Server-side `/api/data` returns 200 in <500ms. Server-side product page HTML has the button. But the client-side React Query fetch never fires and `waitForSelector` times out after 30s. Fresh cycles inherit the same broken state. Zero orders placed.

## Root cause

Chromium's certificate-error bypass — whether set via the raw command-line flag `--ignore-certificate-errors` or via Puppeteer's `acceptInsecureCerts: true` launch option (which flips the same switch via CDP `Security.setIgnoreCertificateErrors`) — breaks fetch scheduling / hydration on **plain-HTTP origins** in Chromium 142 headless. On HTTPS origins with valid certs the flag is inert and no bug shows. On HTTP-only origins the flag corrupts internal network-process state and every `page.evaluate` / `waitForSelector` / fetch on that browser afterwards misbehaves.

## Reproduction

From inside the loadgen pod on any deploy pointing `RUM_FRONTEND_IP` at an `http://…` URL:

```js
const puppeteer = require('puppeteer');
const args = ['--no-sandbox','--disable-setuid-sandbox','--disable-web-security', /* full loadgen args */];
async function trial(opts) {
  const b = await puppeteer.launch(opts);
  const p = await (await b.createBrowserContext()).newPage();
  await p.goto('http://<host>/', {waitUntil:'networkidle2'});
  await p.goto('http://<host>/product/L9ECAV7KIM', {waitUntil:'networkidle2'});
  try { await p.waitForSelector("[data-cy=product-add-to-cart]", {timeout:15000}); console.log('OK'); }
  catch { console.log('MISS'); }
  await b.close();
}
await trial({headless:true, args});                              // OK
await trial({headless:true, args, acceptInsecureCerts:true});    // MISS
await trial({headless:true, args:[...args,'--ignore-certificate-errors']}); // MISS
```

## Why EU never hit it

`astronomy-shop-eu` uses `https://astronomy-shop-eu.splunko11y.com` with a **valid** cert. `--ignore-certificate-errors` was still active in Chromium, but with valid certs it never engaged the buggy code path. EU produced ~150 cycles/hour, ~50% orders, without issue.

`o11y-2026` used `http://…splunk.show:81` (plain HTTP, non-standard port). The flag engaged its buggy code path immediately. Every cycle broken from #1.

## Fix

Both flags removed from `puppeteer.launch()` args in `astronomy-loadgen-k8s.yaml`. Only `--allow-insecure-localhost` remains (which is safe — it whitelists localhost specifically, no side-effects on remote origins).

## If HTTPS-with-self-signed is ever required

Do NOT restore either flag globally. Instead, gate on the target URL scheme:

```js
const needsInsecureBypass = /^https:\/\//i.test(process.env.RUM_FRONTEND_IP || '');
const browser = await puppeteer.launch({
  headless: true,
  acceptInsecureCerts: needsInsecureBypass,   // only when target is HTTPS
  args: [...],
});
```

That keeps HTTP deploys clean while still allowing HTTPS-self-signed deploys to work.

## History

- `1e256e41` (2026-06-01, v2.0.4): both flags added, motivated by self-signed HTTPS ingress support. Never validated against HTTP-only deploys.
- 2026-07-30: `--ignore-certificate-errors` removed after full bisection on `o11y-2026`. `--allow-insecure-localhost` retained (harmless).
