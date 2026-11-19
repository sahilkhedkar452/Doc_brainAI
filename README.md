# DocBrain AI

PDF question answering with text extraction, overlapping chunks, local sentence-transformer embeddings, vector similarity retrieval, and an optional LLM answer grounded in retrieved passages.

## Run locally

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment, then run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and add an API key for generated answers. Without a key, the app still performs semantic retrieval and displays the source passages.
4. Run `streamlit run app.py`.

The embedding model is downloaded the first time it is used. Uploaded files and vectors stay in the Streamlit session; this starter version does not persist documents between sessions. Scanned PDFs need OCR before upload.
