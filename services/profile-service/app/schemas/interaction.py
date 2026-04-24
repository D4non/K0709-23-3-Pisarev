from pydantic import BaseModel, Field


class InteractionRequest(BaseModel):
    viewer_telegram_id: int
    candidate_telegram_id: int
    action: str = Field(pattern="^(like|skip)$")


class InteractionResponse(BaseModel):
    success: bool
    is_match: bool = False
    candidate_name: str | None = None
    viewer_name: str | None = None
