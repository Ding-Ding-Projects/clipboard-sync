import asyncio,json,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
async def main():
 results=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for language in ['en','zh-HK','both']:
   for width in [320,1440]:
    context=await browser.new_context(viewport={'width':width,'height':1000})
    page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto('http://127.0.0.1:4175')
    await page.locator('.nav-item[data-page="settings"]').click()
    await page.locator('#language').select_option(language)
    for name in ['settings','help','history','workspace']:
     await page.locator(f'.nav-item[data-page="{name}"]').click()
     text=await page.locator('body').inner_text()
     assert '${' not in text,(language,name,text)
     if language=='zh-HK':
      for raw in ['Your content stays yours.','Start Clipboard Sync on your PC','A few preferences.','Open the complete setup guide','Connect your receiver before saving relay settings.']:
       assert raw not in text,(name,raw)
     assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),(language,width,name)
    await page.locator('#message').fill('Draft survives language and page changes')
    await page.locator('.nav-item[data-page="settings"]').click()
    await page.locator('.nav-item[data-page="workspace"]').click()
    assert await page.locator('#message').input_value()=='Draft survives language and page changes'
    await page.locator('[data-action="setup"]').click()
    assert await page.locator('[data-action="wizard-next"]').evaluate('(element) => element.disabled')
    await page.reload()
    assert await page.evaluate("localStorage.getItem('language')")==language
    await page.goto('http://127.0.0.1:4175/send')
    assert '${' not in await page.locator('body').inner_text()
    assert await page.locator('[data-action="send"]').evaluate('(element) => element.disabled')
    await page.locator('[data-mode="file"]').click()
    await page.locator('#file').wait_for()
    assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'),(language,width,'phone')
    if width==320:
     shot=ROOT/'design/evidence'/f'phone-offline-{language}.png'
     await page.screenshot(path=str(shot),full_page=True)
    assert not errors,errors
    results.append({'language':language,'width':width,'checks':['localized surface text','no template interpolation leaks','no horizontal overflow','draft survives navigation','offline setup blocked','language persisted after reload','phone file tab opens','offline send blocked'],'pageErrors':errors})
    await context.close()
  await browser.close()
 receipt={'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'capturedAt':datetime.now(timezone.utc).isoformat(),'route':'linux-playwright-headless','buildCommand':'npm run build','artifactFiles':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'dist').rglob('*') if p.is_file()},'captures':[{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'screen':'phone file sender','state':'offline','language':p.stem.removeprefix('phone-offline-'),'theme':'light','viewport':{'width':320,'height':1000,'scale':1}} for p in sorted((ROOT/'design/evidence').glob('phone-offline-*.png'))],'results':results,'scope':'Offline real production bundle; no API mocks or DOM injection. No native Windows clipboard assertion.','privacy':'No credentials, QR codes, records, private paths or device identities supplied.'}
 (ROOT/'design/evidence/localization-checks.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('Passed',len(results),'language/viewport flows')
asyncio.run(main())
