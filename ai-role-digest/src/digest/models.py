from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Post(BaseModel):
    id: str
    url: str
    text: str
    author_name: str
    author_headline: str
    author_url: str
    posted_at: Optional[datetime] = None
    query: str = ""


class OutreachDraft(BaseModel):
    title: str
    connection_request: str
    direct_message: str


class ScoredPost(BaseModel):
    post: Post
    score: int
    role_match: bool
    reason: str
    poster_name: str
    poster_url: str
    outreach: Optional[OutreachDraft] = None
