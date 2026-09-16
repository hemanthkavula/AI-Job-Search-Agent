from __future__ import annotations
from app.browser.common import fill_first

async def fill_greenhouse(page, candidate: dict, resume_path: str | None=None) -> list[dict]:
    """Fill common Greenhouse fields. Does NOT click final submit."""
    results=[]
    mapping={
      "first_name": ["#first_name","input[name='job_application[first_name]']"],
      "last_name": ["#last_name","input[name='job_application[last_name]']"],
      "email": ["#email","input[type='email']"],
      "phone": ["#phone","input[type='tel']"],
      "linkedin": ["input[autocomplete='url']","input[name*='linkedin' i]"],
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
