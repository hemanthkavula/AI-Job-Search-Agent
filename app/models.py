from pydantic import BaseModel, Field
from typing import Optional

class JobInput(BaseModel):
    company: str
    title: str
    description: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    url: Optional[str] = None

class JobAnalysis(BaseModel):
    company: str
    title: str
    score: int = Field(ge=0, le=100)
    decision: str
    matched_skills: list[str]
    missing_skills: list[str]
    reasons: list[str]
    requires_review: bool = True
