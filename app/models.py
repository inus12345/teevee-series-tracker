from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class CatalogTitle(Base):
    __tablename__ = "catalog_titles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    media_type = Column(String(50), nullable=False)
    year = Column(Integer, nullable=True)
    source = Column(String(100), nullable=False)
    source_url = Column(String(255), nullable=True)
    external_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    library_entries = relationship("LibraryEntry", back_populates="catalog_title")


class LibraryEntry(Base):
    __tablename__ = "library_entries"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    status = Column(String(50), default="planned")
    downloaded = Column(Boolean, default=False)
    watched = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    catalog_id = Column(Integer, ForeignKey("catalog_titles.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    catalog_title = relationship("CatalogTitle", back_populates="library_entries")
