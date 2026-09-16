"""Real Chromium/WebGPU lifecycle checks; no API provider or browser-security override."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    out=Path('verification/renderer');out.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[];failure=None
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'),args=[
            '--enable-unsafe-webgpu','--use-webgpu-adapter=swiftshader',
            '--use-angle=swiftshader','--use-vulkan=swiftshader','--enable-features=Vulkan'])
        page=await browser.new_page(viewport={'width':1024,'height':800})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        try:
            await page.goto('http://127.0.0.1:8088/?test=1')
            await page.wait_for_function("document.documentElement.dataset.renderer==='WebGPU'")
            # Explicit test fixture uses the shipped module, not an alternate renderer.
            await page.evaluate('''async()=>{
                const {OrbRenderer}=await import('./src/renderer.js');
                const c=document.createElement('canvas');c.tabIndex=0;c.id='lifetime-fixture';
                c.style.cssText='position:fixed;left:0;top:0;width:320px;height:240px;z-index:999';
                document.body.append(c);window.fixture=new OrbRenderer(c,()=>{});
                fixture.paused=true;await fixture.init();
            }''')
            await page.wait_for_function('fixture.frames>=1&&!fixture.gpuBusy')
            assert await page.evaluate("fixture.kind==='WebGPU'")
            checks.append('Shipped renderer compiles and submits a real WebGPU frame')
            assert await page.evaluate('''async()=>{
                const a=fixture.loadCAD(),b=fixture.loadCAD();
                if(a!==b)return false;const names=await a;fixture.cad=true;
                return names.length>=26&&fixture.meshes.length===names.length;
            }''')
            await page.wait_for_function('!fixture.gpuBusy&&fixture.frames>=2')
            checks.append('Concurrent CAD load shares one real GPU upload transaction')
            before=await page.evaluate('fixture.frames');await page.wait_for_timeout(350)
            assert await page.evaluate('fixture.frames')==before
            checks.append('Stationary CAD submits no redundant frames')
            await page.locator('#lifetime-fixture').focus();await page.keyboard.press('ArrowRight')
            await page.wait_for_function('fixture.params.yaw>0&&!fixture.gpuBusy')
            await page.keyboard.press('Home');await page.wait_for_function('fixture.params.yaw===0')
            checks.append('Focused-canvas keyboard orbit and reset')
            # Device destruction exercises the same lost-device route as a reset.
            await page.evaluate('fixture.device.destroy()')
            await page.wait_for_function("fixture.kind==='Canvas 2D'&&fixture.device===null")
            assert await page.evaluate('fixture.meshes.length===0&&!fixture.loadedCAD&&!fixture.cad')
            await page.locator('#lifetime-fixture').focus();await page.keyboard.press('ArrowLeft')
            assert await page.evaluate('fixture.params.yaw<0')
            checks.append('Device loss releases GPU ownership and reinstalls fallback input')
            await page.evaluate('fixture.dispose();fixture.dispose()')
            before=await page.evaluate('fixture.frames');await page.wait_for_timeout(250)
            assert await page.evaluate('fixture.frames')==before
            checks.append('Idempotent disposal stops all frame submissions')
            assert not errors,errors
        except Exception as exc:
            failure=repr(exc);raise
        finally:
            (out/'report.json').write_text(json.dumps({'passed':not failure and not errors and len(checks)==6,
                'checks':checks,'failure':failure,'errors':errors,
                'gpu':'Chromium software adapter; no hardware performance claim','provider':'NONE'},indent=2)+'\n')
            await browser.close()

if __name__=='__main__':asyncio.run(main())
