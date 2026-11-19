"""DocBrain AI: PDF question answering with local embeddings and optional LLM answers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import streamlit as st
from dotenv import load_dotenv
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

load_dotenv()


@dataclass
class Chunk:
    text: str
    source: str
    page: int


@st.cache_resource(show_spinner="Loading the local embedding model…")
def get_embedder() -> SentenceTransformer:
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def split_text(text: str, size: int = 180, overlap: int = 35) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        if words[start:end]:
            chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdfs(files: list[Any]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for uploaded in files:
        reader = PdfReader(uploaded)
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for piece in split_text(text):
                chunks.append(Chunk(piece, uploaded.name, page_number))
    return chunks


def rank_chunks(question: str, chunks: list[Chunk], vectors: np.ndarray, top_k: int = 5) -> list[tuple[Chunk, float]]:
    query = get_embedder().encode([question], normalize_embeddings=True)[0]
    scores = vectors @ query
    order = np.argsort(scores)[::-1][: min(top_k, len(chunks))]
    return [(chunks[int(i)], float(scores[int(i)])) for i in order]


def answer_with_llm(question: str, results: list[tuple[Chunk, float]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ""
    from openai import OpenAI

    context = "\n\n".join(
        f"[Source: {chunk.source}, page {chunk.page}]\n{chunk.text}" for chunk, _ in results
    )
    client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.1,
        messages=[
            {"role": "system", "content": "Answer using only the supplied document excerpts. If they do not contain the answer, say so. Cite sources as [filename, page N]."},
            {"role": "user", "content": f"Question: {question}\n\nDocument excerpts:\n{context}"},
        ],
    )
    return response.choices[0].message.content or "No answer was returned."


def main() -> None:
    st.set_page_config(page_title="DocBrain AI", page_icon="📚", layout="wide")
    st.title("📚 DocBrain AI")
    st.caption("Upload PDFs, search their meaning, and ask questions grounded in the source pages.")
    with st.sidebar:
        st.header("Your documents")
        uploads = st.file_uploader("Choose PDF files", type=["pdf"], accept_multiple_files=True)
        top_k = st.slider("Source passages per answer", 1, 8, 5)
        if st.button("Clear document index", use_container_width=True):
            for key in ("docbrain_chunks", "docbrain_vectors", "docbrain_names"):
                st.session_state.pop(key, None)

    if uploads:
        names = [f"{file.name}:{file.size}" for file in uploads]
        if names != st.session_state.get("docbrain_names"):
            try:
                with st.spinner("Reading PDFs and creating embeddings…"):
                    chunks = extract_pdfs(uploads)
                    if not chunks:
                        st.warning("No selectable text was found. Scanned PDFs need OCR before they can be indexed.")
                        return
                    vectors = get_embedder().encode([c.text for c in chunks], normalize_embeddings=True, show_progress_bar=False)
                st.session_state.docbrain_chunks = chunks
                st.session_state.docbrain_vectors = np.asarray(vectors, dtype=np.float32)
                st.session_state.docbrain_names = names
                st.success(f"Indexed {len(chunks)} passages from {len(uploads)} PDF(s).")
            except Exception as exc:
                st.error(f"Could not process the PDFs: {exc}")

    chunks = st.session_state.get("docbrain_chunks", [])
    vectors = st.session_state.get("docbrain_vectors")
    if not chunks or vectors is None:
        st.info("Upload one or more PDFs to begin. The first run downloads the embedding model.")
        return

    question = st.text_input("Ask a question about your documents", placeholder="What are the main findings?")
    if question:
        try:
            results = rank_chunks(question, chunks, vectors, top_k)
            with st.spinner("Preparing an answer from the retrieved passages…"):
                answer = answer_with_llm(question, results)
            if answer:
                st.subheader("Answer")
                st.write(answer)
            else:
                st.info("No OPENAI_API_KEY is configured. Showing the closest source passages as a retrieval-only answer.")
                st.subheader("Most relevant passages")
                st.write("\n\n".join(f"**{c.source}, page {c.page}** · similarity {score:.2f}\n\n{c.text}" for c, score in results))
            with st.expander("Retrieved source passages"):
                for chunk, score in results:
                    st.markdown(f"**{chunk.source}, page {chunk.page}** · {score:.3f}")
                    st.write(chunk.text)
        except Exception as exc:
            st.error(f"Search or answer generation failed: {exc}")


if __name__ == "__main__":
    main()
