import os
import glob
import torch
from typing import List, Dict, Any
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from Llm import llm
import pickle
import gc
import shutil


class RAGSystem:
    def __init__(self, data_folder: str = "data", faiss_index_path: str = "faiss_index"):
        """
        Initialize RAG System
        
        Args:
            data_folder (str): Path to folder containing markdown files
            faiss_index_path (str): Path to save/load FAISS index
        """
        self.data_folder = data_folder
        self.faiss_index_path = faiss_index_path
        self.embedding_model = None
        self.vectorstore = None
        self.documents = []
        self.chunks = []
        
        # Check GPU availability
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🚀 Using device: {self.device}")
        if self.device == "cuda":
            print(f"📊 GPU: {torch.cuda.get_device_name(0)}")
            print(f"💾 VRAM Available: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    def load_markdown_files(self) -> List[Document]:
        """
        Load all markdown files from the data folder
        
        Returns:
            List[Document]: List of loaded documents
        """
        print("📁 Loading markdown files...")
        documents = []
        
        # Create data folder if it doesn't exist
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
            print(f"Created data folder: {self.data_folder}")
            return documents
        
        # Find all markdown files
        markdown_files = glob.glob(os.path.join(self.data_folder, "*.md")) + \
                        glob.glob(os.path.join(self.data_folder, "*.markdown"))
        
        if not markdown_files:
            print("⚠️ No markdown files found in the data folder")
            return documents
        
        # Load each markdown file
        for file_path in markdown_files:
            try:
                loader = TextLoader(file_path, encoding='utf-8')
                file_docs = loader.load()
                
                # Add metadata
                for doc in file_docs:
                    doc.metadata['source'] = os.path.basename(file_path)
                    doc.metadata['file_path'] = file_path
                
                documents.extend(file_docs)
                print(f"✅ Loaded: {os.path.basename(file_path)}")
                
            except Exception as e:
                print(f"❌ Error loading {file_path}: {str(e)}")
        
        self.documents = documents
        print(f"📊 Total documents loaded: {len(documents)}")
        return documents

    def chunk_documents(self, chunk_size: int = 800, chunk_overlap: int = 200) -> List[Document]:
        """
        Split documents into chunks for better retrieval
        
        Args:
            chunk_size (int): Size of each chunk
            chunk_overlap (int): Overlap between chunks
            
        Returns:
            List[Document]: List of document chunks
        """
        print("✂️ Chunking documents...")
        
        if not self.documents:
            print("⚠️ No documents to chunk. Load documents first.")
            return []
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        chunks = text_splitter.split_documents(self.documents)
        self.chunks = chunks
        
        print(f"📊 Created {len(chunks)} chunks")
        return chunks

    def create_embeddings(self, model_name: str = "intfloat/e5-base-v2"):
        """
        Create embedding model with GPU support
        
        Args:
            model_name (str): HuggingFace model name for embeddings
        """
        print(f"🤖 Creating embedding model: {model_name}")
        
        # GPU-optimized configuration
        model_kwargs = {
            'device': self.device,
            'trust_remote_code': True
            # 'torch_dtype': torch.float16 if self.device == "cuda" else torch.float32,
        }
        
        # Additional GPU optimizations (reduced batch size for e5-large-v2 as it's larger)
        encode_kwargs = {
            'normalize_embeddings': True,
            'batch_size': 16 if self.device == "cuda" else 8,  # Smaller batch for larger model
        }
        
        self.embedding_model = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs,
            show_progress=True  # Use the correct parameter name
        )
        
        print("✅ Embedding model created")
        if self.device == "cuda":
            print("🚀 GPU acceleration enabled for embeddings")

    def create_vector_store(self):
        """
        Create FAISS vector store from document chunks with GPU acceleration
        """
        print("🗄️ Creating FAISS vector store...")
        
        if not self.chunks:
            print("⚠️ No chunks available. Chunk documents first.")
            return
        
        if not self.embedding_model:
            print("⚠️ No embedding model. Create embeddings first.")
            return
        
        # Process chunks in batches to optimize GPU memory usage (smaller batches for e5-large-v2)
        batch_size = 50 if self.device == "cuda" else 25
        
        if len(self.chunks) > batch_size:
            print(f"📦 Processing {len(self.chunks)} chunks in batches of {batch_size}")
            
            # Create initial vector store with first batch
            first_batch = self.chunks[:batch_size]
            self.vectorstore = FAISS.from_documents(first_batch, self.embedding_model)
            
            # Add remaining chunks in batches
            for i in range(batch_size, len(self.chunks), batch_size):
                batch = self.chunks[i:i+batch_size]
                batch_vectorstore = FAISS.from_documents(batch, self.embedding_model)
                self.vectorstore.merge_from(batch_vectorstore)
                print(f"📈 Processed {min(i+batch_size, len(self.chunks))}/{len(self.chunks)} chunks")
        else:
            # Create FAISS vector store directly for smaller datasets
            self.vectorstore = FAISS.from_documents(self.chunks, self.embedding_model)
        
        print("✅ FAISS vector store created")

    def save_vector_store(self):
        """
        Save FAISS vector store to disk
        """
        if not self.vectorstore:
            print("⚠️ No vector store to save")
            return
        
        print(f"💾 Saving vector store to {self.faiss_index_path}")
        self.vectorstore.save_local(self.faiss_index_path)
        print("✅ Vector store saved")

    def load_vector_store(self):
        """
        Load FAISS vector store from disk
        """
        if not os.path.exists(self.faiss_index_path):
            print(f"⚠️ No saved vector store found at {self.faiss_index_path}")
            return False
        
        if not self.embedding_model:
            print("⚠️ Create embedding model first")
            return False
        
        print(f"📂 Loading vector store from {self.faiss_index_path}")
        try:
            self.vectorstore = FAISS.load_local(
                self.faiss_index_path, 
                self.embedding_model,
                allow_dangerous_deserialization=True
            )
            print("✅ Vector store loaded")
            return True
        except Exception as e:
            print(f"❌ Error loading vector store: {str(e)}")
            return False

    def setup_retriever(self, k: int = 300):
        """
        Setup document retriever
        
        Args:
            k (int): Number of documents to retrieve
        """
        print("🔗 Setting up document retriever...")
        
        if not self.vectorstore:
            print("⚠️ No vector store available. Create or load vector store first.")
            return
        
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )
        
        print("✅ Document retriever setup complete")

    def create_rag_prompt(self, question: str, context_docs: List[Document]) -> str:
        # Combine context from retrieved documents
        context = "\n\n".join([
            f"Document: {doc.metadata.get('source', 'Unknown')}\n{doc.page_content}"
            for doc in context_docs
        ])
        
        prompt = f"""You are a helpful AI assistant. Use the following context to answer the user's question. If the answer cannot be found in the context, say so clearly.

Context:
{context}

Question: {question}

Answer: """
        
        return prompt

    def query(self, question: str) -> Dict[str, Any]:
        if not hasattr(self, 'retriever') or not self.retriever:
            return {"error": "Retriever not setup. Call setup_retriever() first."}
        
        print(f"\n🔍 Query: {question}")
        
        try:
            # Clear GPU cache before retrieval for optimal memory usage
            if self.device == "cuda":
                torch.cuda.empty_cache()
            
            # Retrieve relevant documents using the new invoke method
            relevant_docs = self.retriever.invoke(question)
            
            if not relevant_docs:
                return {
                    "answer": "No relevant documents found for your question.",
                    "sources": []
                }
            
            # Create RAG prompt
            rag_prompt = self.create_rag_prompt(question, relevant_docs)
            
            # Get answer from custom LLM
            answer = llm.ask_gemini(rag_prompt)
            
            response = {
                "answer": answer,
                "sources": []
            }
            
            # Extract source information
            for doc in relevant_docs:
                source_info = {
                    "content": doc.page_content ,
                    "source": doc.metadata.get("source", "Unknown"),
                    "file_path": doc.metadata.get("file_path", "Unknown")
                }
                response["sources"].append(source_info)
            
            return response
            
        except Exception as e:
            return {"error": f"Error during query: {str(e)}"}

    def ask(self , prompt: str, question: str) -> Dict[str, Any]:
        print(f"\n🔍 Query: {question}")
        
        try:
            # Clear GPU cache before retrieval for optimal memory usage
            if self.device == "cuda":
                torch.cuda.empty_cache()
                
            # Retrieve relevant documents using the new invoke method
            relevant_docs = self.retriever.invoke(question)
            
            if not relevant_docs:
                return {
                    "answer": "No relevant documents found for your question.",
                    "sources": []
                }
            
            # Create RAG prompt
            rag_prompt = self.create_rag_prompt(question, relevant_docs)
            rag_prompt += prompt
            
            # Get answer from custom LLM
            answer = llm.ask_gemini(rag_prompt)
            
            response = {
                "answer": answer,
                "sources": []
            }
            
            # Extract source information
            for doc in relevant_docs:
                source_info = {
                    "content": doc.page_content ,
                    "source": doc.metadata.get("source", "Unknown"),
                    "file_path": doc.metadata.get("file_path", "Unknown")
                }
                response["sources"].append(source_info)
            
            return response
            
        except Exception as e:
            return {"error": f"Error during query: {str(e)}"}
        
    def build_from_scratch(self):
        """
        Build the complete RAG system from scratch
        """
        print("🚀 Building RAG system from scratch...")
        
        # Load documents
        self.load_markdown_files()
        
        # Chunk documents
        self.chunk_documents()
        
        # Create embeddings
        self.create_embeddings()
        
        # Create vector store
        self.create_vector_store()
        
        # Save vector store
        self.save_vector_store()
        
        # Setup retriever
        self.setup_retriever()
        
        print("🎉 RAG system ready!")

    def load_existing_system(self):
        """
        Load existing RAG system from saved vector store
        """
        print("📂 Loading existing RAG system...")
        
        # Create embeddings (needed for loading vector store)
        self.create_embeddings()
        
        # Load vector store
        if not self.load_vector_store():
            print("❌ Could not load existing system. Build from scratch instead.")
            return False
        
        # Setup retriever
        self.setup_retriever()
        
        print("✅ RAG system loaded and ready!")
        return True
    
    def cleanup(self):
        print("🧹 Cleaning up GPU memory and FAISS index...")
        if self.device == "cuda":
            # Delete model references
            del self.embedding_model
            if hasattr(self, 'retriever'):
                del self.retriever
            if hasattr(self, 'vectorstore'):
                del self.vectorstore
            torch.cuda.empty_cache()
            gc.collect()
            print("✅ GPU memory cleared")
        else:
            print("ℹ️ No GPU cleanup needed on CPU")
        
        # Delete FAISS index folder if it exists
        if hasattr(self, 'faiss_index_path') and os.path.exists(self.faiss_index_path):
            try:
                shutil.rmtree(self.faiss_index_path)
                print(f"🗑️ Deleted FAISS index folder: {self.faiss_index_path}")
            except Exception as e:
                print(f"⚠️ Error deleting FAISS index folder: {e}")
        else:
            print("ℹ️ No FAISS index folder to delete")
