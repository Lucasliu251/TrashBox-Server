from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ServiceMedalState = Literal["unknown", "yes", "no"]


class ResolveRequest(BaseModel):
    value: str = Field(min_length=2, max_length=255)


class RadarTargetCreate(BaseModel):
    steam_id: str = Field(pattern=r"^7656119\d{10}$")
    alias: Optional[str] = Field(default=None, max_length=100)
    tags: List[str] = Field(default_factory=list, max_length=20)
    note: Optional[str] = Field(default=None, max_length=500)
    manual_cs_level: Optional[int] = Field(default=None, ge=0, le=100)
    service_medal: ServiceMedalState = "unknown"


class RadarTargetUpdate(BaseModel):
    alias: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[List[str]] = Field(default=None, max_length=20)
    note: Optional[str] = Field(default=None, max_length=500)
    manual_cs_level: Optional[int] = Field(default=None, ge=0, le=100)
    service_medal: Optional[ServiceMedalState] = None


class RadarSessionCreate(BaseModel):
    duration_seconds: int = Field(default=600, ge=60, le=600)
