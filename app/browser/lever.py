from __future__ import annotations
from app.browser.common import fill_first

async def fill_lever(page, candidate: dict, resume_path: str | None=None) -> list[dict]:
    """Fill common Lever fields. Does NOT click final submit."""
    results=[]
    mapping={
      "name": ["input[name='name']"],
      "email": ["input[name='email']","input[type='email']"],
      "phone": ["input[name='phone']","input[type='tel']"],
      "linkedin": ["input[name='urls[LinkedIn]']","input[placeholder*='LinkedIn' i]"],
    }
    for field,selectors in mapping.items():
        value=candidate.get(field)
        if value:
            r=await fill_first(page,selectors,value,field)
            results.append(r.__dict__)
    if resume_path:
        upload=page.locator("input[type='file']")
        if await upload.count():
            await upload.first.set_input_files(resume_path)
            results.append({"field":"resume","status":"uploaded"})
    return results
