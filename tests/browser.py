"""Chromium/WebGPU end-to-end checks. Paid AI is mocked; CSP is never bypassed."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path('verification/browser')
OUT.mkdir(parents=True, exist_ok=True)
TOKEN = 'browser-test-device-token-not-a-secret'

async def main():
    errors, checks = [], []
    failure = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'), args=[
            '--enable-unsafe-webgpu', '--use-angle=swiftshader', '--enable-features=Vulkan',
            '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
        context = await browser.new_context(viewport={'width':1440,'height':1000},
                                             device_scale_factor=1, permissions=['microphone'])
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        try:
            await page.goto('http://127.0.0.1:8088/?test=1')
            # Playwright string expressions use eval under CSP; pass a function instead.
            await page.wait_for_function("() => document.documentElement.dataset.renderer === 'WebGPU'", timeout=45000)
            checks.append('WebGPU pipeline created; software adapter in CI')
            await page.screenshot(path=str(OUT/'01-studio.png'), full_page=True)
            await page.locator('#question').fill('What might I discover in a new beginning?')
            await page.locator('#ask').click()
            await page.wait_for_function("() => document.querySelector('#stage-state').textContent === 'A MOMENT TO REFLECT'")
            assert await page.locator('#reflection').is_visible()
            checks.append('demo reading and teller projection')
            await page.screenshot(path=str(OUT/'02-teller.png'), full_page=True)
            await page.locator('[data-view=client]').click()
            assert not await page.locator('#reflection').is_visible()
            checks.append('client perspective hides projected answer')
            await page.locator('[data-view=split]').click()
            await page.screenshot(path=str(OUT/'03-compare.png'), full_page=True)
            await page.locator('#engineering').click()
            await page.wait_for_selector('.part')
            assert await page.locator('.part').count() >= 26
            await page.locator('#explode').evaluate("el => { el.value='70'; el.dispatchEvent(new Event('input',{bubbles:true})); }")
            await page.wait_for_timeout(250)
            await page.screenshot(path=str(OUT/'04-cad-exploded.png'), full_page=True)
            checks.append('CAD tessellation loaded and exploded')
            await page.locator('.part button').first.click()
            await page.locator('#isolate').click()
            await page.locator('#show-all').click()
            await page.locator('#experience').click()
            await page.locator('#settings-open').click()
            await page.locator('#gateway-url').fill('http://127.0.0.1:8088')
            await page.locator('#device-token').fill(TOKEN)
            await page.locator('#connect-form button[type=submit]').click()
            await page.wait_for_selector('#connection.live')
            await page.wait_for_timeout(100)
            await page.locator('#question').fill('A mock integration question')
            await page.locator('#ask').click()
            await page.wait_for_function("() => document.querySelector('#stage-state').textContent === 'A MOMENT TO REFLECT'")
            assert 'fictional reflection' in await page.locator('#answer').text_content()
            checks.append('authenticated Responses stream through real gateway; mocked provider')
            assert await page.evaluate('() => localStorage.length + sessionStorage.length') == 0
            checks.append('no credential or transcript browser storage')
            await page.locator('#speak').click()
            await page.wait_for_function("() => document.querySelector('#stage-state').textContent === 'A MOMENT TO REFLECT'")
            checks.append('bounded PCM playback')
            await page.locator('#record').hover()
            await page.mouse.down()
            await page.wait_for_timeout(1100)
            await page.mouse.up()
            await page.wait_for_function("() => document.querySelector('#stage-state').textContent === 'A MOMENT TO REFLECT'", timeout=15000)
            checks.append('AudioWorklet capture, WAV resampling, mocked STT and response')
            await page.locator('#erase').click()
            assert not await page.locator('#reflection').is_visible()
            assert 'erased' in await page.locator('#answer').text_content()
            checks.append('explicit private response erasure')
            await page.set_viewport_size({'width':390,'height':844})
            await page.screenshot(path=str(OUT/'05-mobile.png'), full_page=True)
            assert await page.evaluate('() => document.documentElement.scrollWidth <= innerWidth')
            checks.append('390 px mobile layout without horizontal overflow')
            client = await context.new_page()
            await client.goto('http://127.0.0.1:8088/?client=1&test=1')
            await client.wait_for_selector('body.public')
            assert not await client.locator('#operator-console').is_visible()
            checks.append('separate client page exposes no operator interface')
            await client.close()
            await page.set_viewport_size({'width':1440,'height':1000})
            await page.goto('http://127.0.0.1:8088/?renderer=canvas&test=1')
            await page.wait_for_function("() => document.documentElement.dataset.renderer === 'Canvas 2D'")
            await page.screenshot(path=str(OUT/'06-fallback.png'), full_page=True)
            checks.append('explicit Canvas 2D fallback')
            if errors:
                raise AssertionError(errors)
        except Exception as exc:
            failure = repr(exc)
            try:
                await page.screenshot(path=str(OUT/'failure.png'), full_page=True)
            except Exception:
                pass
            raise
        finally:
            (OUT/'report.json').write_text(json.dumps({
                'passed': failure is None and not errors and len(checks) >= 12,
                'checks': checks, 'errors': errors, 'failure': failure,
                'provider': 'MOCKED; no live OpenAI key used',
                'gpu': 'Chromium software WebGPU; not hardware FPS qualification',
                'csp': 'Production CSP unchanged; no unsafe-eval or bypassCSP'
            }, indent=2)+'\n')
            await browser.close()
    print(json.dumps({'passed':len(checks), 'checks':checks}, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
