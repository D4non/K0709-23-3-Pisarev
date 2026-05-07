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


class PhotoOut(BaseModel):
    id: int
    url: str
    object_key: str
    is_primary: bool

    model_config = {"from_attributes": True}


class AddPhotoRequest(BaseModel):
    object_key: str
    url: str
    is_primary: bool = False


class ProfileResponse(BaseModel):
    telegram_id: int
    name: str
    age: int
    gender: str
    city: str
    bio: str | None
    interests: list[str]
    photos: list[PhotoOut] = []

    model_config = {"from_attributes": True}


class RegisterUserResponse(BaseModel):
    user_id: int
    telegram_id: int
    message: str


class MatchedProfile(BaseModel):
    telegram_id: int
    name: str
    age: int
    city: str
    primary_photo_object_key: str | None = None


class StatsResponse(BaseModel):
    likes_received: int
    skips_received: int
    likes_given: int
    matches: int
    photos_count: int
    registered_at: str
