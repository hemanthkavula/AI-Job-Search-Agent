from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

async def prepare(url: str, adapter: str, candidate: dict, resume: str | None, headless: bool=False):
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=headless)
        page=await browser.new_page()
        await page.goto(url,wait_until="domcontentloaded",timeout=60000)
        if adapter=="greenhouse":
            from app.browser.greenhouse import fill_greenhouse
            result=await fill_greenhouse(page,candidate,resume)
        elif adapter=="lever":
            from app.browser.lever import fill_lever
            result=await fill_lever(page,candidate,resume)
        else:
            raise ValueError("Supported adapters: greenhouse, lever")
        print(json.dumps(result,indent=2))
        print("\nApplication prepared. Review the browser manually. Final submission is not automated.")
        if not headless:
            await page.pause()
        await browser.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--url",required=True)
    ap.add_argument("--adapter",choices=["greenhouse","lever"],required=True)
    ap.add_argument("--candidate",default="data/application_profile.json")
    ap.add_argument("--resume")
    ap.add_argument("--headless",action="store_true")
    args=ap.parse_args()
    candidate=json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    asyncio.run(prepare(args.url,args.adapter,candidate,args.resume,args.headless))
