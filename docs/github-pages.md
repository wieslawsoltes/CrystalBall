# GitHub Pages browser deployment

The public address is `https://wieslawsoltes.github.io/CrystalBall/` after the Pages deployment succeeds. This is the HTML/JavaScript/WebGPU application, not the Python gateway or a device-control server. It opens in explicitly labeled offline demo mode and makes no AI API calls until the operator pairs a gateway and chooses a live feature.

The Pages workflow stages only tracked `web/index.html`, `web/style.css` and allowed source/assets, never the whole repository. It scans for obvious key material, writes a source-commit and per-file SHA-256 manifest to `build.json`, runs JavaScript tests and eight browser checks at `/CrystalBall/`, then publishes through the official Pages artifact/deployment actions. CSP remains enabled. No service worker, transcript persistence, analytics or third-party frontend CDN is installed. The scanner is a secondary guard, not a substitute for source review.

## Pairing a gateway from Pages

Deploy the gateway at an HTTPS origin with a certificate your browser trusts. Add exactly `https://wieslawsoltes.github.io` to the gateway's `CORS_ORIGINS` environment setting and restart it. The CORS entry is an **origin**: do not add `/CrystalBall/` or a trailing slash, and do not use `*`. Keep your API project key in the gateway environment. Use the separate device token in the browser's Connect gateway dialog. CORS is not authentication; bearer-token validation still applies. All projects on this GitHub Pages hostname share an origin. Use the gateway-hosted application on a dedicated trusted origin for sensitive operation.

Pages cannot host Python, keep an API key secret, reach a private gateway on behalf of a remote visitor, or bypass browser private-network/mixed-content restrictions. For a LAN gateway, the client device must be on the appropriate network and explicitly trust its public CA; browsers may require a local-network permission. Never disable TLS or browser security. When the browser's network policy prevents cross-origin LAN pairing, open the gateway-hosted HTTPS application instead.

## Repository configuration

The repository's Pages source must be **GitHub Actions**. The workflow uses `pages: write` and an OIDC deployment token, not a project API key. If Pages has never been enabled, an owner/maintainer must select Settings > Pages > Build and deployment > Source > GitHub Actions. Normal workflow tokens cannot enable a previously disabled Pages site. Then run **Publish browser to GitHub Pages** from Actions. Subsequent changes under `web/` trigger testing and deployment automatically.

The test evidence uses Chromium's software WebGPU adapter; it does not qualify actual mobile graphics performance or physical optics. The generated `build.json` identifies the actual published source independently of the newer project `main` commit.

References: GitHub's custom Pages workflow documentation and `actions/starter-workflows/pages/static.yml` (reviewed 2026-09-16).
