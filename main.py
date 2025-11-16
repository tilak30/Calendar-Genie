import os
import time
import logging
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.settings import Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# --- Configuration ---
# Setup logging to see what the server is doing
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
INDEX_DIR = "./index_storage"  # Directory to store the index
DOCS_DIR = "./local_files"    # Directory to watch for new files

# --- Models & App Initialization ---
# Use a local embedding model from Hugging Face. BAAI/bge-small-en-v1.5 is a good, lightweight choice.
# The first time you run this, it will be downloaded automatically.
logging.info("Loading embedding model...")
embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

app = FastAPI()

class SearchRequest(BaseModel):
    meeting_name: str
    meeting_description: str | None = None

# --- Core RAG Logic ---

def build_or_rebuild_index():
    """
    Loads documents from DOCS_DIR, creates a vector index, and saves it to disk.
    This function is called on startup and when new files are detected.
    """
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)

    logging.info("Starting to build or rebuild index...")
    # Load all documents from the directory
    documents = SimpleDirectoryReader(DOCS_DIR).load_data()

    if not documents:
        logging.warning("No documents found in 'local_files'. The index will be empty.")
        # Create an empty index to avoid errors on first run
        index = VectorStoreIndex.from_documents([], embed_model=embed_model)
    else:
        # Create the index from the loaded documents
        logging.info(f"Found {len(documents)} document(s). Indexing...")
        # Configure a node parser to split documents into smaller chunks
        node_parser = SentenceSplitter(chunk_size=256, chunk_overlap=20)
        # Configure global settings
        Settings.embed_model = embed_model
        Settings.node_parser = node_parser
        # The index will automatically use the global settings
        index = VectorStoreIndex.from_documents(documents)

    # Persist the index to disk for later use
    index.storage_context.persist(persist_dir=INDEX_DIR)
    logging.info(f"✅ Index has been successfully built and saved to '{INDEX_DIR}'.")

# --- File Monitoring Service using Watchdog ---

class NewFileHandler(FileSystemEventHandler):
    """A handler for file system events that triggers an index rebuild."""
    def on_created(self, event):
        if not event.is_directory:
            logging.info(f"✅ New file detected: {event.src_path}. Triggering index rebuild.")
            # Wait a moment for the file to be fully written to disk
            time.sleep(1)
            build_or_rebuild_index()

def start_file_monitor():
    """Starts the watchdog observer in a separate thread."""
    event_handler = NewFileHandler()
    observer = Observer()
    observer.schedule(event_handler, DOCS_DIR, recursive=True)
    observer.start()
    logging.info(f"👀 Watching for new files in '{DOCS_DIR}'...")
    try:
        # The thread will run this loop forever
        while True:
            time.sleep(60)
    except Exception:
        observer.stop()
        logging.info("File watcher stopped.")
    observer.join()

# --- FastAPI Endpoints ---

@app.on_event("startup")
def on_startup():
    """
    This function runs when the FastAPI application starts.
    It performs the initial index build and starts the file monitor in a background thread.
    """
    # Run the initial index build
    build_or_rebuild_index()

    # Start the file monitor in a background thread
    monitor_thread = Thread(target=start_file_monitor, daemon=True)
    monitor_thread.start()

# Mount the `static` directory so files like JS/CSS are served under `/static`.
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    # If static directory is missing or cannot be mounted, continue without failing the app.
    logging.warning("Could not mount static directory. Static files will not be served.")

@app.post("/api/search")
def search_local_context(request: SearchRequest):
    """
    Searches the local RAG index for context related to the user's query.
    """
    try:
        # 1. Construct an effective search query from the meeting details.
        search_query = request.meeting_name
        if request.meeting_description:
            search_query += f" - {request.meeting_description}"

        # 1. Load the persisted index from disk
        logging.info(f"Loading index for query: '{search_query}'")
        storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
        # Configure the embed model for loading the index
        Settings.embed_model = embed_model

        index = load_index_from_storage(storage_context)

        # 2. Create a retriever to search the index. This only fetches context and does not require an LLM.
        # similarity_top_k=3 means it will retrieve the 3 most relevant text chunks.
        retriever = index.as_retriever(similarity_top_k=3)

        # 3. Execute the retrieval against the index
        retrieved_nodes = retriever.retrieve(search_query)

        # 4. Check if the RAG search found any sufficiently relevant documents.
        # We check the score of the top result. If it's too low, we ignore it.
        SIMILARITY_THRESHOLD = 0.7
        if not retrieved_nodes or retrieved_nodes[0].score < SIMILARITY_THRESHOLD:
            logging.warning("No relevant context found in local files for the query.")
            return {
                "query": search_query,
                "answer": "", # Return an empty answer if no context is found
                "source": "local_rag_empty"
            }

        # 5. Prepare the context for the LLM by combining the text from the retrieved chunks.
        context_for_llm = "\n\n---\n\n".join([node.get_content() for node in retrieved_nodes])
        source_files = sorted(list({node.metadata.get('file_name', 'Unknown') for node in retrieved_nodes}))
        logging.info(f"Found relevant context from chunks in files: {source_files}")

        # 6. Return the raw context as the "answer"
        return {
            "query": search_query,
            "answer": context_for_llm,
            "source": "local_rag_success",
            "source_files": source_files
        }

    except FileNotFoundError:
        logging.error(f"Index directory '{INDEX_DIR}' not found. Please restart the server.")
        raise HTTPException(status_code=500, detail="Index not found. Please ensure the server has started correctly.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search")
def search_local_context_get():
    """Simple helper for GET requests to `/api/search` to guide callers.
    The endpoint primarily accepts POST requests with a JSON body. This GET
    returns usage instructions to avoid 405 responses from clients that try
    to call GET by mistake.
    """
    return {
        "detail": "Use POST /api/search with JSON body: {\n  \"meeting_name\": \"...\",\n  \"meeting_description\": \"optional\"\n}\n",
    }


@app.get("/health")
def health_check():
    """Simple health endpoint for load balancers or monitoring."""
    return {"status": "ok"}


@app.get("/favicon.ico")
def favicon():
    """Return 204 No Content for favicon requests when no file exists to
    avoid noisy 404 logs. If you prefer serving a real favicon, add
    `favicon.ico` to the `static/` directory and mount StaticFiles.
    """
    return Response(status_code=204)


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
def catch_all(full_path: str):
    """
    Catch-all route to handle requests to non-existent paths.
    This provides a more helpful error message than a generic 404.
    """
    # Check if the user is trying to call the main chat API on the RAG server
    if "api/chat" in full_path:
        raise HTTPException(
            status_code=404,
            detail="Not Found: The /api/chat endpoint is on the main server (port 8000), not the RAG server (port 5002)."
        )
    raise HTTPException(status_code=404, detail=f"Not Found: The path '/{full_path}' does not exist on the RAG server.")
