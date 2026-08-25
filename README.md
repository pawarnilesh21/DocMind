# DocMind – AI Document Intelligence Platform

DocMind is a retrieval-augmented generation (RAG) platform that ingests arbitrary documents and answers natural-language questions with source-cited, hallucination-checked responses. It features a modular ingestion pipeline—chunking, embedding generation, and vector storage—paired with a FastAPI backend for document management, chat history, and metadata persistence. Multiple query modes (Q&A, summarization, and an optional LangGraph agent for query routing) let users interact with their documents flexibly. Gemini handles embedding generation while Groq powers fast LLM inference, each chosen for what it's actually built for. A manual evaluation set measures retrieval precision and citation accuracy to keep answers grounded.

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python, FastAPI |
| **LLM Orchestration** | LangChain, LangGraph |
| **Embeddings** | Gemini API (`gemini-embedding-001`) |
| **LLM Inference** | Groq API (`llama-3.3-70b-versatile`) |
| **Vector Store** | ChromaDB |
| **Database** | PostgreSQL |
| **Containerization** | Docker |

