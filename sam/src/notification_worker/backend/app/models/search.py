"""Search request and result models for OpenSearch docket search (Phase 8.6).

Defines structured query parameters, sanitized search item projections,
and pagination models.

INVARIANT: OpenSearch is a searchable projection, NOT an authorization source.
Projection strictly omits passwords, tokens, owner_id, and unneeded internal data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class DocketSearchParams(BaseModel):
    """Sanitized, structured search query parameters for civic dockets."""

    q: Optional[str] = Field(default=None, max_length=200, description="Free-text search query across title, description, and location")
    department: Optional[str] = Field(default=None, description="Department filter")
    status: Optional[str] = Field(default=None, description="Case status filter (e.g. DOCKET_CREATED, IN_PROGRESS)")
    category: Optional[str] = Field(default=None, description="Category filter")
    from_date: Optional[datetime] = Field(default=None, description="Inclusive start timestamp")
    to_date: Optional[datetime] = Field(default=None, description="Inclusive end timestamp")
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Number of results per page (max 100)")
    sort_by: str = Field(default="updated_at", description="Field to sort by: updated_at, created_at, status")
    sort_order: str = Field(default="desc", description="Sort direction: asc or desc")

    @field_validator("q", mode="after")
    @classmethod
    def sanitize_query_string(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned if cleaned else None

    @field_validator("sort_by", mode="after")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        allowed = {"updated_at", "created_at", "status", "case_id"}
        if v not in allowed:
            return "updated_at"
        return v

    @field_validator("sort_order", mode="after")
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        if v.lower() in ("asc", "desc"):
            return v.lower()
        return "desc"


class DocketSearchItem(BaseModel):
    """Sanitized search result item returned to authorized authority workflows."""

    case_id: str
    title: Optional[str] = None
    description: str
    category: Optional[str] = None
    department: str
    status: str
    pincode: Optional[str] = None
    location: str
    location_source: Optional[str] = None
    recommended_department: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    relevance_score: Optional[float] = None


class DocketSearchResult(BaseModel):
    """Bounded, paginated search response."""

    items: List[DocketSearchItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class RebuildIndexResult(BaseModel):
    """Outcome of an administrative docket index reconciliation / rebuild."""

    total_authoritative_cases: int
    successfully_indexed: int
    failed_indexing: int
    errors: List[str] = Field(default_factory=list)
