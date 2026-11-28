from dataclasses import dataclass
import re
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.ai.config import get_ai_settings
from app.ai.permissions import is_hr
from app.ai.rag.embeddings import cosine_similarity, generate_embeddings
from app.models.ai import AIDocument, AIDocumentChunk, AIProviderConfig
from app.models.user import User


@dataclass
class RetrievedChunk:
    document_id: int
    document_title: str
    category: str
    chunk_index: int
    content: str
    score: float


def _keyword_score(query: str, content: str) -> float:
    q_terms = {t for t in re.findall(r"[a-z0-9]{2,}", query.lower())}
    if not q_terms:
        return 0.0
    c_lower = content.lower()
    hits = sum(1 for term in q_terms if term in c_lower)
    return hits / len(q_terms)


def _allowed_visibility_filter(user: User):
    allowed = ["organization"]
    if is_hr(user):
        allowed.append("hr_admin")
    return or_(
        AIDocument.visibility.in_(allowed),
        (AIDocument.visibility == "private") & (AIDocument.uploaded_by == user.id),
    )


async def retrieve_relevant_chunks(
    db: Session,
    user: User,
    query: str,
    *,
    top_k: int = 4,
    min_score: float = 0.2,
) -> list[RetrievedChunk]:
    """Retrieve organization- and RBAC-scoped RAG chunks via pgvector or portable fallback."""
    if not query.strip():
        return []

    org_cfg = (
        db.query(AIProviderConfig)
        .filter(AIProviderConfig.organization_id == user.organization_id)
        .first()
    )
    settings = get_ai_settings()
    query_vecs = await generate_embeddings(
        [query],
        provider_name=org_cfg.active_provider if org_cfg else settings.default_provider,
        embedding_model=org_cfg.embedding_model if org_cfg else settings.default_embedding_model,
        settings=settings,
    )
    query_vec = query_vecs[0] if query_vecs else None

    # Fast PostgreSQL pgvector path when available
    if query_vec and db.bind is not None and db.bind.dialect.name == "postgresql":
        has_col = db.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'ai_document_chunks' AND column_name = 'embedding_vector'"
            )
        ).scalar()
        if has_col:
            allowed_vis = ["organization", "hr_admin"] if is_hr(user) else ["organization"]
            vec_literal = "[" + ",".join(str(float(x)) for x in query_vec) + "]"
            rows = db.execute(
                text(
                    "SELECT d.id, d.title, d.category, c.chunk_index, c.content, "
                    "1 - (c.embedding_vector <=> CAST(:qvec AS vector)) AS score "
                    "FROM ai_document_chunks c "
                    "JOIN ai_documents d ON d.id = c.document_id "
                    "WHERE c.organization_id = :org_id "
                    "AND d.status = 'indexed' "
                    "AND c.embedding_vector IS NOT NULL "
                    "AND (d.visibility = ANY(:vis) OR (d.visibility = 'private' AND d.uploaded_by = :uid)) "
                    "ORDER BY c.embedding_vector <=> CAST(:qvec AS vector) ASC "
                    "LIMIT :lim"
                ),
                {
                    "qvec": vec_literal,
                    "org_id": user.organization_id,
                    "vis": allowed_vis,
                    "uid": user.id,
                    "lim": top_k,
                },
            ).fetchall()
            results = [
                RetrievedChunk(
                    document_id=int(r[0]),
                    document_title=str(r[1]),
                    category=str(r[2]),
                    chunk_index=int(r[3]),
                    content=str(r[4]),
                    score=round(float(r[5]), 4),
                )
                for r in rows
                if float(r[5]) >= min_score
            ]
            if results:
                return results

    # Portable cosine + keyword scoring fallback (SQLite tests or unembedded docs)
    candidates = (
        db.query(AIDocumentChunk, AIDocument)
        .join(AIDocument, AIDocument.id == AIDocumentChunk.document_id)
        .filter(
            AIDocumentChunk.organization_id == user.organization_id,
            AIDocument.status == "indexed",
            _allowed_visibility_filter(user),
        )
        .limit(300)
        .all()
    )

    scored: list[RetrievedChunk] = []
    for chunk, doc in candidates:
        vec_score = (
            cosine_similarity(query_vec, chunk.embedding)
            if (query_vec and chunk.embedding)
            else 0.0
        )
        kw_score = _keyword_score(query, chunk.content)
        combined = max(vec_score, kw_score) if not (query_vec and chunk.embedding) else (0.75 * vec_score + 0.25 * kw_score)
        if combined >= min_score:
            scored.append(
                RetrievedChunk(
                    document_id=doc.id,
                    document_title=doc.title,
                    category=doc.category,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    score=round(float(combined), 4),
                )
            )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]
