"""Capture an offline production build without credentials or synthetic history.
Run a static server for dist first, then: python design/capture-built.py --url URL
Requires Python Playwright and Chromium. This is browser evidence, not Windows proof.
"""
import argparse, asyncio, hashlib, json, subprocess
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'design'/'evidence'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
async def main(url):
 OUT.mkdir(exist_ok=True)
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 assets={str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'dist').rglob('*') if p.is_file()}
 receipt={'version':1,'sourceCommit':commit,'capturedAt':datetime.now(timezone.utc).isoformat(),'route':'linux-playwright-headless','artifactFiles':assets,'buildCommand':'npm run build','scope':'Offline browser rendering; no Windows clipboard or native window proof','tuples':[],'captures':[]}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in [320,1440]:
   for scale in [1,1.25,1.5,2]:
    for language in ['en','zh-HK','both']:
     for theme in ['light','dark']:
      context=await browser.new_context(viewport={'width':width,'height':1000},device_scale_factor=scale)
      page=await context.new_page(); errors=[]
      page.on('pageerror',lambda e:errors.append(str(e)))
      await page.add_init_script(f"localStorage.setItem('language',{json.dumps(language)});localStorage.setItem('theme',{json.dumps(theme)});")
      await page.goto(url);await page.wait_for_timeout(100)
      measurement=await page.evaluate('''() => {const selectors=['.main','.workspace-grid','.composer','.connection','.sidebar'];return {overflow:document.documentElement.scrollWidth>innerWidth,elements:selectors.map(selector=>{const e=document.querySelector(selector),r=e.getBoundingClientRect(),s=getComputedStyle(e);return {selector,matchedCount:document.querySelectorAll(selector).length,rect:r.toJSON(),computed:Object.fromEntries(['display','position','boxSizing','width','height','overflowX','overflowY','fontSize','lineHeight','gap','gridTemplateColumns'].map(k=>[k,s[k]]))}})}}''')
      receipt['tuples'].append({'screen':'D1','state':'offline','width':width,'height':1000,'displayScale':scale,'language':language,'theme':theme,'errors':errors,**measurement})
      if width==1440 and scale==1 and language=='en' and theme=='light':
       for name in ['workspace','history','settings','help','setup']:
        if name in ['history','settings','help']:await page.locator(f'.nav-item[data-page="{name}"]').click()
        if name=='setup':await page.locator('[data-action="setup"]').first.click()
        await page.wait_for_timeout(100)
        shot=OUT/f'{name}-offline.png';await page.screenshot(path=str(shot),full_page=True)
        receipt['captures'].append({'path':shot.name,'sha256':digest(shot),'screen':name,'state':'offline','viewport':{'width':width,'height':1000,'scale':scale},'language':language,'theme':theme})
      await context.close()
  await browser.close()
 receipt['sourceEndCommit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 receipt['limitations']=['No native Windows process or window handles.','The Windows-only receipt validator requires a different route and was not used.','Complete screen/state matrix and screen-reader behavior remain unverified.','Display scale varies device pixel ratio; OS text scaling is not established.']
 (OUT/'browser-layout.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps({'tuples':len(receipt['tuples']),'overflow':sum(t['overflow'] for t in receipt['tuples']),'pageErrors':sum(len(t['errors']) for t in receipt['tuples'])}))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:4173');asyncio.run(main(parser.parse_args().url))
