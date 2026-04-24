from pydantic import BaseModel, Field


class RegisterUserRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    name: str = Field(min_length=2, max_length=100)
    age: int = Field(ge=18, le=99)
    gender: str = Field(pattern="^(male|female)$")
    city: str = Field(min_length=2, max_length=100)
    bio: str | None = None
    interests: list[str] = []
    # Browsing preferences (optional at registration)
    min_age: int = Field(default=18, ge=18, le=99)
    max_age: int = Field(default=99, ge=18, le=99)
    preferred_gender: str | None = Field(default=None, pattern="^(male|female)$")


class ProfileResponse(BaseModel):
    telegram_id: int
    name: str
    age: int
    gender: str
    city: str
    bio: str | None
    interests: list[str]

    model_config = {"from_attributes": True}


class RegisterUserResponse(BaseModel):
    user_id: int
    telegram_id: int
    message: str
