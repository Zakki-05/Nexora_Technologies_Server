import asyncio
import io
import zipfile
import httpx

from app.ai.rag.chunking import chunk_text, extract_text_from_bytes
from app.ai.rag.retrieval import retrieve_relevant_chunks
from app.models.organization import Organization


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    buf = io.BytesIO()
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_chunking_and_docx_extraction():
    docx = _make_docx_bytes(["Nexora Leave Policy", "Employees get 18 annual leave days."])
    extracted = extract_text_from_bytes(
        "policy.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        docx,
    )
    assert "Nexora Leave Policy" in extracted
    assert "18 annual leave days" in extracted

    long_text = " ".join(["workforce"] * 300)
    chunks = chunk_text(long_text, chunk_size=400, overlap=60)
    assert len(chunks) >= 4
    assert all(len(c) <= 450 for c in chunks)


def test_rag_document_upload_visibility_and_citations(
    client, db_session, employee_user, admin_user, employee_headers, admin_headers, monkeypatch
):
    org = Organization(id=1, name="Nexora Technologies", slug="nexora", company_code="NEX-001")
    db_session.merge(org)
    db_session.commit()

    # Employee cannot upload or delete RAG documents
    denied = client.post(
        "/ai/documents",
        files={"file": ("policy.txt", b"Annual leave carry forward is 5 days.", "text/plain")},
        data={"title": "Leave Policy", "category": "hr_policy", "visibility": "organization"},
        headers=employee_headers,
    )
    assert denied.status_code == 403

    # Admin uploads public org document and an HR-only document
    pub_res = client.post(
        "/ai/documents",
        files={
            "file": (
                "leave_policy.md",
                b"# Leave Policy\nEmployees are entitled to 18 annual leave days and 5 carry-forward days.",
                "text/markdown",
            )
        },
        data={"title": "2026 Leave Handbook", "category": "hr_policy", "visibility": "organization"},
        headers=admin_headers,
    )
    assert pub_res.status_code == 201
    pub_doc = pub_res.json()["data"]
    assert pub_doc["status"] == "indexed"
    assert pub_doc["chunk_count"] >= 1

    hr_res = client.post(
        "/ai/documents",
        files={
            "file": (
                "hr_internal.txt",
                b"Confidential HR salary band revision guideline for Q4.",
                "text/plain",
            )
        },
        data={"title": "Confidential HR Bands", "category": "compensation", "visibility": "hr_admin"},
        headers=admin_headers,
    )
    assert hr_res.status_code == 201

    # Employee only sees organization-visible doc, not hr_admin doc
    emp_docs = client.get("/ai/documents", headers=employee_headers).json()["data"]
    assert len(emp_docs) == 1
    assert emp_docs[0]["title"] == "2026 Leave Handbook"

    emp_hits = asyncio.run(
        retrieve_relevant_chunks(db_session, employee_user, "salary band revision guideline")
    )
    assert emp_hits == []

    adm_hits = asyncio.run(
        retrieve_relevant_chunks(db_session, admin_user, "salary band revision guideline")
    )
    assert len(adm_hits) == 1
    assert adm_hits[0].document_title == "Confidential HR Bands"

    # Chat returns RAG citations from 2026 Leave Handbook
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    client.put("/ai/config", json={"is_enabled": True}, headers=admin_headers)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(":generateContent"):
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": "According to the 2026 Leave Handbook, employees receive 18 annual leave days."
                                    }
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 14, "totalTokenCount": 44},
                },
            )
        if request.url.path.endswith(":batchEmbedContents"):
            return httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2, 0.3]}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real_async_client(*a, **{**kw, "transport": transport}))

    chat_res = client.post(
        "/ai/chat",
        json={"message": "How many annual leave days and carry forward days are in the leave handbook?"},
        headers=employee_headers,
    )
    assert chat_res.status_code == 200
    msg = chat_res.json()["data"]["message"]
    assert msg["citations"] is not None
    assert msg["citations"][0]["title"] == "2026 Leave Handbook"
