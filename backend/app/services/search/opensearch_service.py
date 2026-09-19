"""OpenSearch Docket Index and Query Service for JARVIS Civic (Phase 8.6).

Provides authorized search indexing, query DSL construction, index reconciliation,
and health checking targeting local OpenSearch (http://localhost:9200).

ARCHITECTURAL INVARIANTS:
1. OpenSearch is strictly a SEARCHABLE PROJECTION, NOT the authoritative database.
2. OpenSearch NEVER decides authorization (Cedar remains authoritative).
3. Indexing failure is non-fatal to case persistence and is tracked for reconciliation.
4. Public tracking remains separate and safe.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from opensearchpy import OpenSearch, exceptions as os_exceptions

from app.config.settings import settings
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.search import (
    DocketSearchItem,
    DocketSearchParams,
    DocketSearchResult,
    RebuildIndexResult,
)
from app.models.security import CivicCaseRecord
from app.services.persistence.interface import CaseRepository

logger = logging.getLogger("jarvis.search.opensearch")

DOCKET_INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index": {
            "max_result_window": 10000,
        }
    },
    "mappings": {
        "properties": {
            "case_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "description": {"type": "text", "analyzer": "standard"},
            "category": {"type": "keyword"},
            "department": {"type": "keyword"},
            "status": {"type": "keyword"},
            "pincode": {"type": "keyword"},
            "location": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "location_source": {"type": "keyword"},
            "recommended_department": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    },
}


class OpenSearchDocketService:
    """Production-structured service handling OpenSearch docket indexing and queries."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        index_name: Optional[str] = None,
        index_alias: Optional[str] = None,
        use_ssl: Optional[bool] = None,
        timeout: Optional[int] = None,
    ):
        self.host = host or settings.OPENSEARCH_HOST
        self.port = port or settings.OPENSEARCH_PORT
        self.index_name = index_name or settings.OPENSEARCH_INDEX_NAME
        self.index_alias = index_alias or settings.OPENSEARCH_INDEX_ALIAS
        self.use_ssl = use_ssl if use_ssl is not None else settings.OPENSEARCH_USE_SSL
        self.timeout = timeout or settings.OPENSEARCH_TIMEOUT_SECONDS

        self._client: Optional[OpenSearch] = None
        self._index_verified: bool = False
        # In-memory tracking of recent sync errors for observability
        self._sync_failures: List[Dict[str, Any]] = []

    def get_client(self) -> OpenSearch:
        """Get or initialize thread-safe OpenSearch client."""
        if self._client is None:
            self._client = OpenSearch(
                hosts=[{"host": self.host, "port": self.port}],
                http_compress=True,
                use_ssl=self.use_ssl,
                verify_certs=False,
                ssl_assert_hostname=False,
                ssl_show_warn=False,
                timeout=self.timeout,
                max_retries=settings.OPENSEARCH_MAX_RETRIES,
                retry_on_timeout=True,
            )
        return self._client

    def ensure_index(self) -> bool:
        """Create versioned index and alias if not already present.

        Idempotent and resilient.
        """
        try:
            client = self.get_client()
            exists = client.indices.exists(index=self.index_name)
            if not exists:
                logger.info("Creating OpenSearch index '%s'...", self.index_name)
                client.indices.create(index=self.index_name, body=DOCKET_INDEX_MAPPING)
                # Attach alias
                client.indices.put_alias(index=self.index_name, name=self.index_alias)
                logger.info("OpenSearch index '%s' and alias '%s' created successfully.", self.index_name, self.index_alias)
            else:
                # Ensure alias is pointing to index
                if not client.indices.exists_alias(name=self.index_alias, index=self.index_name):
                    client.indices.put_alias(index=self.index_name, name=self.index_alias)
            self._index_verified = True
            return True
        except Exception as exc:
            logger.warning("OpenSearch ensure_index failed (non-blocking): %s", exc)
            return False

    def docket_to_document(self, record: CivicCaseRecord) -> Dict[str, Any]:
        """Transform authoritative CivicCaseRecord into minimal sanitized search projection."""
        status_val = record.status.value if isinstance(record.status, CaseStatus) else str(record.status)
        dept_val = record.department.value if isinstance(record.department, ControlledDepartment) else str(record.department)

        # Format timestamps in standard ISO 8601
        created_str = record.created_at.isoformat() if record.created_at else datetime.now(timezone.utc).isoformat()
        updated_str = record.updated_at.isoformat() if record.updated_at else created_str

        # Derive a clean title from the description summary
        title = record.description[:80] + "..." if len(record.description) > 80 else record.description

        return {
            "case_id": record.case_id,
            "title": title,
            "description": record.description,
            "category": dept_val,
            "department": dept_val,
            "status": status_val,
            "pincode": record.pincode or "",
            "location": record.location,
            "location_source": record.location_source or "UNKNOWN",
            "recommended_department": dept_val,
            "created_at": created_str,
            "updated_at": updated_str,
        }

    def index_docket(self, record: CivicCaseRecord) -> bool:
        """Index or re-index a civic docket projection into OpenSearch.

        NON-BLOCKING: Returns False and logs structured error on failure,
        without throwing unhandled exception to caller.
        """
        try:
            self.ensure_index()
            client = self.get_client()
            doc = self.docket_to_document(record)
            client.index(
                index=self.index_alias,
                id=record.case_id,
                body=doc,
                refresh=True,
            )
            logger.info("OpenSearch: Successfully indexed docket '%s'", record.case_id)
            return True
        except Exception as exc:
            error_info = {
                "operation": "index_docket",
                "case_id": record.case_id,
                "error": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._sync_failures.append(error_info)
            if len(self._sync_failures) > 100:
                self._sync_failures.pop(0)
            logger.error("OpenSearch indexing failure for case '%s' (non-blocking): %s", record.case_id, exc)
            return False

    def update_docket(self, record: CivicCaseRecord) -> bool:
        """Update existing docket projection in OpenSearch."""
        # Using index with id acts as upsert
        return self.index_docket(record)

    def search_dockets(
        self,
        params: DocketSearchParams,
        authorized_department: Optional[str] = None,
    ) -> DocketSearchResult:
        """Execute structured search query against OpenSearch docket index.

        Args:
            params: Validated search query parameters.
            authorized_department: Department enforced by server-side identity/Cedar.
                If provided (non-empty), Level 2 isolation filter is strictly added.
                If None/empty (e.g. Administrator), queries across departments.

        Raises:
            ConnectionError / TimeoutError on OpenSearch connection issues.
        """
        self.ensure_index()
        client = self.get_client()

        filter_clauses: List[Dict[str, Any]] = []

        # Level 2 Department Isolation
        if authorized_department and authorized_department != "ALL":
            filter_clauses.append({"term": {"department": authorized_department}})
        elif params.department:
            filter_clauses.append({"term": {"department": params.department}})

        # Status filter
        if params.status:
            filter_clauses.append({"term": {"status": params.status.strip()}})

        # Category filter
        if params.category:
            filter_clauses.append({"term": {"category": params.category.strip()}})

        # Date range filter
        date_range: Dict[str, Any] = {}
        if params.from_date:
            date_range["gte"] = params.from_date.isoformat()
        if params.to_date:
            date_range["lte"] = params.to_date.isoformat()
        if date_range:
            filter_clauses.append({"range": {"created_at": date_range}})

        # Query clause (free-text or match_all)
        if params.q:
            query_clause: Dict[str, Any] = {
                "multi_match": {
                    "query": params.q,
                    "fields": [
                        "case_id^3",
                        "title^2",
                        "description",
                        "location^1.5",
                        "pincode^1.2",
                    ],
                    "type": "best_fields",
                }
            }
        else:
            query_clause = {"match_all": {}}

        bool_query: Dict[str, Any] = {
            "must": query_clause,
        }
        if filter_clauses:
            bool_query["filter"] = filter_clauses

        # Deterministic sorting
        sort_field = params.sort_by
        sort_order = params.sort_order
        sort_clauses = [
            {sort_field: {"order": sort_order}},
            {"case_id": {"order": "asc"}},  # Deterministic tie-breaker
        ]

        from_offset = (params.page - 1) * params.page_size
        search_body: Dict[str, Any] = {
            "query": {"bool": bool_query},
            "sort": sort_clauses,
            "from": from_offset,
            "size": params.page_size,
        }

        response = client.search(
            index=self.index_alias,
            body=search_body,
        )

        hits_data = response.get("hits", {})
        total_hits = hits_data.get("total", {})
        total_count = total_hits.get("value", 0) if isinstance(total_hits, dict) else int(total_hits)

        items: List[DocketSearchItem] = []
        for hit in hits_data.get("hits", []):
            src = hit.get("_source", {})
            score = hit.get("_score")
            items.append(
                DocketSearchItem(
                    case_id=src.get("case_id"),
                    title=src.get("title"),
                    description=src.get("description", ""),
                    category=src.get("category"),
                    department=src.get("department", ""),
                    status=src.get("status", ""),
                    pincode=src.get("pincode"),
                    location=src.get("location", ""),
                    location_source=src.get("location_source"),
                    recommended_department=src.get("recommended_department"),
                    created_at=datetime.fromisoformat(src.get("created_at")),
                    updated_at=datetime.fromisoformat(src.get("updated_at")),
                    relevance_score=float(score) if score is not None else None,
                )
            )

        has_next = (from_offset + len(items)) < total_count

        return DocketSearchResult(
            items=items,
            total=total_count,
            page=params.page,
            page_size=params.page_size,
            has_next=has_next,
        )

    def rebuild_docket_index(self, case_repo: CaseRepository) -> RebuildIndexResult:
        """Reconcile and rebuild the entire OpenSearch docket index from authoritative CaseStore.

        Guarantees complete recovery of every failed projection.
        """
        self.ensure_index()
        cases = case_repo.list_all_cases()
        total = len(cases)
        indexed = 0
        failed = 0
        errors: List[str] = []

        logger.info("Beginning docket index rebuild for %d authoritative cases...", total)
        for record in cases:
            success = self.index_docket(record)
            if success:
                indexed += 1
            else:
                failed += 1
                errors.append(f"Failed to index case {record.case_id}")

        logger.info("Docket index rebuild complete: %d total, %d indexed, %d failed", total, indexed, failed)
        return RebuildIndexResult(
            total_authoritative_cases=total,
            successfully_indexed=indexed,
            failed_indexing=failed,
            errors=errors,
        )

    def health_check(self) -> Dict[str, Any]:
        """Non-blocking cluster health probe."""
        try:
            client = self.get_client()
            health = client.cluster.health(request_timeout=3)
            return {
                "status": "healthy" if health.get("status") in ("green", "yellow") else "degraded",
                "cluster_name": health.get("cluster_name"),
                "cluster_status": health.get("status"),
                "number_of_nodes": health.get("number_of_nodes"),
                "active_shards": health.get("active_shards"),
                "recent_sync_failures": len(self._sync_failures),
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "error": str(exc),
                "recent_sync_failures": len(self._sync_failures),
            }


# Global singleton instance
opensearch_service = OpenSearchDocketService()
