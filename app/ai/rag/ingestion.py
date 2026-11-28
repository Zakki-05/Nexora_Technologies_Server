import hashlib
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.config import get_ai_settings
from app.ai.guardrails import record_ai_audit
from app.ai.orchestrator import get_or_create_org_config
from app.ai.rag.chunking import chunk_text, estimate_tokens, extract_text_from_bytes
from app.ai.rag.embeddings import generate_embeddings
from app.models.ai import AIDocument, AIDocumentChunk
from app.models.user import User


async def ingest_document(
    db: Session,
    user: User,
    *,
    title: str,
    filename: str,
    content_type: str,
    raw_bytes: bytes,
    category: str = "hr_policy",
    visibility: str = "organization",
) -> AIDocument:
    """Extract, chunk, optionally embed, and store a knowledge document for RAG."""
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    doc = AIDocument(
        organization_id=user.organization_id,
        uploaded_by=user.id,
        title=title.strip() or filename,
        filename=filename,
        content_type=content_type or "text/plain",
        category=category,
        visibility=visibility,
        status="pending",
        file_size_bytes=len(raw_bytes),
        checksum=checksum,
    )
    db.add(doc)
    db.flush()

    try:
        extracted = extract_text_from_bytes(filename, content_type, raw_bytes)
        chunks = chunk_text(extracted)
        if not chunks:
            raise ValueError("Document contains no extractable text.")

        settings = get_ai_settings()
        org_cfg = get_or_create_org_config(db, user.organization_id)
        embeddings = await generate_embeddings(
            chunks,
            provider_name=org_cfg.active_provider,
            embedding_model=org_cfg.embedding_model,
            settings=settings,
        )

        chunk_rows: list[AIDocumentChunk] = []
        for idx, content in enumerate(chunks):
            vec = embeddings[idx] if embeddings and idx < len(embeddings) else None
            row = AIDocumentChunk(
                document_id=doc.id,
                organization_id=user.organization_id,
                chunk_index=idx,
                content=content,
                token_estimate=estimate_tokens(content),
                embedding=vec,
                metadata_json={"title": doc.title, "category": doc.category, "visibility": doc.visibility},
            )
            db.add(row)
            chunk_rows.append(row)

        db.flush()

        # Populate pgvector column when running on PostgreSQL with pgvector enabled
        if embeddings and db.bind is not None and db.bind.dialect.name == "postgresql":
            has_col = db.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'ai_document_chunks' AND column_name = 'embedding_vector'"
                )
            ).scalar()
            if has_col:
                for row in chunk_rows:
                    if row.embedding:
                        vec_literal = "[" + ",".join(str(float(x)) for x in row.embedding) + "]"
                        db.execute(
                            text(
                                "UPDATE ai_document_chunks "
                                "SET embedding_vector = CAST(:vec AS vector) "
                                "WHERE id = :cid"
                            ),
                            {"vec": vec_literal, "cid": row.id},
                        )

        doc.chunk_count = len(chunk_rows)
        doc.status = "indexed"
        record_ai_audit(
            db,
            user=user,
            action="document_ingest",
            input_summary=f"doc_id={doc.id} title={doc.title} chunks={doc.chunk_count}",
            output_status="success",
        )
        db.commit()
        db.refresh(doc)
        return doc
    except Exception as exc:
        doc.status = "failed"
        doc.error_message = str(exc)[:500]
        record_ai_audit(
            db,
            user=user,
            action="document_ingest",
            input_summary=f"doc_id={doc.id} title={doc.title}",
            output_status="failed",
        )
        db.commit()
        db.refresh(doc)
        raise
