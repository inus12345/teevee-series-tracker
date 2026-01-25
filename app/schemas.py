from typing import Optional

from pydantic import BaseModel


class CatalogTitleBase(BaseModel):
    title: str
    media_type: str
    year: Optional[int] = None
    source: str
    source_url: Optional[str] = None
    external_id: Optional[str] = None
    description: Optional[str] = None
    release_date: Optional[str] = None
    rating: Optional[float] = None


class CatalogTitleResponse(CatalogTitleBase):
    id: int

    class Config:
        orm_mode = True


class LibraryEntryBase(BaseModel):
    title: str
    status: str = "planned"
    downloaded: bool = False
    watched: bool = False
    notes: Optional[str] = None
    catalog_id: Optional[int] = None


class LibraryEntryCreate(LibraryEntryBase):
    pass


class LibraryEntryUpdate(BaseModel):
    status: Optional[str] = None
    downloaded: Optional[bool] = None
    watched: Optional[bool] = None
    notes: Optional[str] = None


class LibraryEntryResponse(LibraryEntryBase):
    id: int

    class Config:
        orm_mode = True
