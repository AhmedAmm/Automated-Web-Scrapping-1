import os
import shutil
import tempfile
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, Dict, Any
import client
import company
import product
from rag1 import RAGSystem
from iterative_rag import systematic_rag_query
from Llm import llm
from all import company_search as full_company_search

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown: Clean up RAG system if it exists
    if hasattr(app.state, 'rag'):
        app.state.rag.cleanup()

app = FastAPI(lifespan=lifespan)

# Request models
class ScrapeClientRequest(BaseModel):
    client: str

class ScrapeProductRequest(BaseModel):
    product: str
    description: str

class AnalyzeCompanyRequest(BaseModel):
    company: str

class QueryRAGRequest(BaseModel):
    question: str
    output_format: Optional[str] = None

class ScrapeAllRequest(BaseModel):
    user_company:   str
    user_product:   str
    description:    str
    client_company: str

# Helper to run CPU-bound tasks in a thread
async def run_in_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)

@app.post("/scrape-client")
async def scrape_client(request: ScrapeClientRequest):
    """Scrape URLs related to a client profile."""
    temp_dir = tempfile.mkdtemp()
    try:
        data_folder = os.path.join(temp_dir, "data")
        os.makedirs(data_folder)
        await client.company_search(request.client)
        return {"message": "Scraping completed"}
    finally:
        shutil.rmtree(temp_dir)

@app.post("/scrape-product")
async def scrape_product(request: ScrapeProductRequest):
    """Scrape URLs related to product competitors."""
    temp_dir = tempfile.mkdtemp()
    try:
        data_folder = os.path.join(temp_dir, "data")
        os.makedirs(data_folder)
        await product.company_search(request.product, request.description)
        return {"message": "Scraping completed", "data_folder": data_folder}
    finally:
        shutil.rmtree(temp_dir)

@app.post("/analyze-company")
async def analyze_company(request: AnalyzeCompanyRequest):
    """Perform competitor and client analysis for a company."""
    temp_dir = tempfile.mkdtemp()
    try:
        data_folder = os.path.join(temp_dir, "data")
        faiss_index_path = os.path.join(temp_dir, "faiss_index")
        os.makedirs(data_folder)
        result = await company.company_search(request.company)
        return result
    finally:
        shutil.rmtree(temp_dir)

@app.post("/initialize-rag")
async def initialize_rag():
    """Initialize the RAG system and LLM on demand."""
    if hasattr(app.state, 'rag'):
        return {"message": "RAG system already initialized"}
    rag = RAGSystem(data_folder="data", faiss_index_path="faiss_index")
    rag.build_from_scratch()
    rag.load_existing_system()
    app.state.rag = rag
    app.state.llm = llm
    return {"message": "RAG system initialized"}

@app.post("/cleanup-rag")
async def cleanup_rag():
    """Clean up the RAG system and LLM manually."""
    if hasattr(app.state, 'rag'):
        app.state.rag.cleanup()
        del app.state.rag
        del app.state.llm
        return {"message": "RAG system cleaned up"}
    return {"message": "RAG system not initialized"}

@app.post("/query-rag")
async def query_rag(request: QueryRAGRequest):
    """Answer a question using systematic RAG query with pre-built RAG system."""
    if not hasattr(app.state, 'rag') or not hasattr(app.state, 'llm'):
        return {"error": "RAG system not initialized"}
    rag_system = app.state.rag
    llm_instance = app.state.llm
    result = await run_in_thread(
        systematic_rag_query,
        request.question,
        rag_system,
        llm_instance,
        output_format_prompt=request.output_format
    )
    return {"answer": result["answer"]}

@app.post("/scrape-all")
async def scrape_all(request: ScrapeAllRequest):
    """Run the full scrape pipeline: generate → search → scrape."""
    await full_company_search(
        user_company=request.user_company,
        product=request.user_product,
        description=request.description,
        client_company=request.client_company
    )
    return {"message": "Scrape-all pipeline completed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)