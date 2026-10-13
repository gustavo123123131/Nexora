# Nexora Chromium Executor (Railway)

**This service is required for real multi-login on the Vercel dashboard.** It runs actual Chromium contexts in an always-on container, isolating profile folders under /data/profiles.

## Deploy once

1. Railway > New Project > Deploy from GitHub > Nexora. Set **Root Directory** to `/runner` so Railway uses runner/Dockerfile. Allocate enough memory (begin at 1–2 GB for a couple of browsers).
2. Add a **persistent Railway Volume** mounted at **`/data`**. Without the volume cookies and logins can be lost on redeploy.
3. Set `NEXORA_RUNNER_KEY` to a randomly generated secret of **32+ characters**. Store securely. Do NOT commit it to GitHub. Optional: `NEXORA_MAX_PROFILES=3`.
4. Settings > Networking > Generate Domain. Use the HTTPS domain, e.g. `https://example.up.railway.app`.
5. In Vercel's **Environment Variables**, set `NEXORA_RUNNER_URL` to this HTTPS domain **without a trailing slash**; redeploy Vercel.
6. Open the Nexora page, click **Conectar navegador**, enter the secret created in step 3. The secret lives only in this tab's sessionStorage; after closing the tab you may need to re-enter it.
7. Click **Abrir** on a profile; the site will render in the Nexora viewer. Use mouse clicks, send text, Tab, Enter, scroll; log in manually. Each profile uses its own Chromium directory.

**Important security:** this exposes interactive authenticated browsing. Only give NEXORA_RUNNER_KEY to trusted users. Railway worker requires it on every request and Vercel forwards it, without logging request bodies. Use HTTPS. No password is required to *view Nexora's metadata*, but controlling browser sessions ALWAYS requires the private key. Do not disable authentication.

**Limitations:** Streaming is screenshot polling rather than full noVNC video; some rich websites, popups, file uploads, anti-bot systems and apps needing native Android may not work. Mobile is Playwright Chromium emulation, not Android. Worker reboots close active browsers but persistent cookies are retained if volume survives. HTTP remote runner via Railway public domain is protected by key.

**No free hosting guarantee:** Railway resource usage and volumes can incur charges. The Vercel UI alone cannot run persistent browsers.

**Legacy:** Local Windows/browser manager remains unchanged. Existing *local* cookie profiles are NOT automatically imported to Railway.
