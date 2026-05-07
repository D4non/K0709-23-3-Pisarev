from pydantic import BaseModel


class PhotoUploadResponse(BaseModel):
    object_key: str
    url: str
