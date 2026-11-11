"""Authentication route placeholder.

Authentication persistence and credential verification are not implemented yet.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["인증"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(_payload: LoginRequest):
    """Reserve the login contract until user storage and token policy are defined."""
    raise HTTPException(status_code=501, detail="인증 기능은 아직 구현되지 않았습니다.")
