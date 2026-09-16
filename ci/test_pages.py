"""Exercise the staged site at /CrystalBall/, not only a convenient root URL."""
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'verification/pages'


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


async def verify(base):
    OUT.mkdir(parents=True, exist_ok=True)
    errors, failures, requests, checks = [], [], [], []
    failure = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'), args=[
            '--enable-unsafe-webgpu', '--use-webgpu-adapter=swiftshader',
            '--use-angle=swiftshader', '--use-vulkan=swiftshader', '--enable-features=Vulkan'])
        context = await browser.new_context(viewport={'width':1440, 'height':1000})
        page = await context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        context.on('request', lambda r: requests.append(r.url))
        context.on('response', lambda r: failures.append({'url':r.url, 'status':r.status}) if r.status >= 400 else None)
        try:
            await page.goto(base + '?test=1')
            await page.wait_for_function("() => !!document.documentElement.dataset.renderer", timeout=45000)
            assert await page.locator('html').get_attribute('data-renderer') == 'WebGPU'
            checks.append('WebGPU module and WGSL load below /CrystalBall/')
            assert 'Demo' in await page.locator('#connection').inner_text()
            await page.locator('#question').fill('A new beginning')
            await page.locator('#ask').click()
            await page.wait_for_function("() => document.querySelector('#stage-state').textContent === 'A MOMENT TO REFLECT'")
            assert await page.locator('#reflection').is_visible()
            await page.screenshot(path=str(OUT / 'teller.png'), full_page=True)
            checks.append('Offline demo reading and teller projection')
            await page.locator('[data-view=client]').click()
            assert not await page.locator('#reflection').is_visible()
            checks.append('Client perspective hides projected text')
            await page.locator('#engineering').click()
            await page.wait_for_selector('.part')
            assert await page.locator('.part').count() >= 26
            await page.locator('#explode').evaluate("el => {el.value='65';el.dispatchEvent(new Event('input',{bubbles:true}));}")
            await page.screenshot(path=str(OUT / 'engineering.png'), full_page=True)
            checks.append('CAD assets load below repository path; explosion works')
            await page.locator('#experience').click()
            await page.set_viewport_size({'width':390, 'height':844})
            await page.screenshot(path=str(OUT / 'mobile.png'), full_page=True)
            assert await page.evaluate('() => document.documentElement.scrollWidth <= innerWidth')
            checks.append('390px layout without horizontal overflow')
            async with context.expect_page() as child:
                await page.locator('#client-window').click()
            public = await child.value
            await public.wait_for_selector('body.public')
            assert public.url.startswith(base + '?client=1')
            assert not await public.locator('#operator-console').is_visible()
            checks.append('Separate client window preserves repository base path')
            await public.close()
            await page.goto(base + '?renderer=canvas&test=1')
            await page.wait_for_function("() => document.documentElement.dataset.renderer === 'Canvas 2D'")
            checks.append('Canvas fallback works on static host')
            assert await page.evaluate('() => localStorage.length + sessionStorage.length') == 0
            assert not any('/v1/' in r or not r.startswith(base) for r in requests)
            assert not errors and not failures, (errors, failures)
            checks.append('No API traffic, browser storage, off-origin or root-relative asset requests')
        except Exception as exc:
            failure = repr(exc)
            await page.screenshot(path=str(OUT / 'failure.png'), full_page=True)
            raise
        finally:
            (OUT / 'report.json').write_text(json.dumps({
                'passed': failure is None and len(checks) == 8 and not errors and not failures,
                'checks':checks, 'errors':errors, 'failed_responses':failures, 'failure':failure,
                'provider':'NONE: static offline demo', 'gpu':'Chromium software adapter; no hardware FPS claim',
                'base_path':'/CrystalBall/', 'csp':'Production meta CSP; not bypassed'
            }, indent=2) + '\n')
            await browser.close()


def main():
    with tempfile.TemporaryDirectory() as folder:
        shutil.copytree(ROOT / '_site', Path(folder) / 'CrystalBall')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=folder))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(verify(f'http://127.0.0.1:{server.server_port}/CrystalBall/'))
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    main()
