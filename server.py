"""
Unified Backend Server - Combines UI Session Management + LLM Conversation Logic
Features:
- Google OAuth authentication
- Meeting preparation and chat
- LLM-powered responses with RAG/Web search
- ElevenLabs audio generation
- Conversation history tracking
"""

import os
import json
import secrets
import httpx
import base64
from datetime import datetime
from typing import Optional, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

import logging
import time
from threading import Thread
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

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# RAG index directories and embedding model
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
INDEX_DIR = "./index_storage"
DOCS_DIR = "./local_files"

logging.info("Loading embedding model for RAG (may download)...")
embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")


class SearchRequest(BaseModel):
    meeting_name: str
    meeting_description: Optional[str] = None


def build_or_rebuild_index():
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)

    logging.info("Starting to build or rebuild index...")
    documents = SimpleDirectoryReader(DOCS_DIR).load_data()

    if not documents:
        logging.warning("No documents found in 'local_files'. The index will be empty.")
        index = VectorStoreIndex.from_documents([], embed_model=embed_model)
    else:
        logging.info(f"Found {len(documents)} document(s). Indexing...")
        node_parser = SentenceSplitter(chunk_size=256, chunk_overlap=20)
        Settings.embed_model = embed_model
        Settings.node_parser = node_parser
        index = VectorStoreIndex.from_documents(documents)

    index.storage_context.persist(persist_dir=INDEX_DIR)
    logging.info(f"✅ Index has been successfully built and saved to '{INDEX_DIR}'.")


class NewFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            logging.info(f"✅ New file detected: {event.src_path}. Triggering index rebuild.")
            time.sleep(1)
            build_or_rebuild_index()


def start_file_monitor():
    event_handler = NewFileHandler()
    observer = Observer()
    observer.schedule(event_handler, DOCS_DIR, recursive=True)
    observer.start()
    logging.info(f"👀 Watching for new files in '{DOCS_DIR}'...")
    try:
        while True:
            time.sleep(60)
    except Exception:
        observer.stop()
        logging.info("File watcher stopped.")
    observer.join()

# Initialize FastAPI app
app = FastAPI(title="Calendar-Genie Backend")

# ============================================================================
# MIDDLEWARE
# ============================================================================
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-in-production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = "http://localhost:8000/auth/callback"

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# OpenRouter (for LLM)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Mock mode
MOCK_AUTH = os.getenv("MOCK_AUTH", "false").lower() == "true"

# Load mock meetings
try:
    with open('meeting.json', 'r') as f:
        MOCK_MEETINGS = json.load(f)['meetings']
except:
    MOCK_MEETINGS = []

# ============================================================================
# IMPORTS - Agent Classes
# ============================================================================
from agents.conversation_agent import ConversationAnalysisAgent
from agents.smart_fetcher import SmartFetcherAgent
from openai import OpenAI

# Initialize agents
decision_agent = ConversationAnalysisAgent()
# Pass RAG server url from env (or default) into the SmartFetcher so it's
# deterministic and easy to configure from the process environment.
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://127.0.0.1:5002")
fetcher_agent = SmartFetcherAgent(rag_server_url=RAG_SERVER_URL)

# Synthesizer client
synthesizer_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# ============================================================================
# DATA MODELS
# ============================================================================

class ChatRequest(BaseModel):
    """Chat request model"""
    query: str
    mock_index: Optional[int] = None  # For mock meetings

class PrepMeetingRequest(BaseModel):
    """Meeting prep request"""
    meetings: bool = False
    mock_index: int = 0
    meeting_data: Optional[Dict] = None

class AudioRequest(BaseModel):
    """Audio generation request"""
    text: str

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

sessions: Dict[str, Dict] = {}

def generate_state() -> str:
    """Generate secure state token"""
    return secrets.token_urlsafe(32)

def create_session(user_data: Dict) -> str:
    """Create user session"""
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user": user_data,
        "meetings": {},  # meeting_session_id -> meeting data
        "conversation_history": {}  # meeting_session_id -> chat history
    }
    return session_id

def get_session(session_id: str) -> Optional[Dict]:
    """Get session by ID"""
    return sessions.get(session_id)

def delete_session(session_id: str) -> None:
    """Delete session"""
    if session_id in sessions:
        del sessions[session_id]

# ============================================================================
# AUDIO GENERATION
# ============================================================================

async def generate_audio_with_elevenlabs(text: str) -> Optional[str]:
    """Generate audio using ElevenLabs API"""
    if not ELEVENLABS_API_KEY:
        return None
    
    try:
        url = f"{ELEVENLABS_API_URL}/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            }
        }
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            audio_bytes = response.content
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            return f"data:audio/mpeg;base64,{audio_b64}"
            
    except Exception as e:
        print(f"⚠️ ElevenLabs error: {str(e)}")
        return None

# ============================================================================
# LLM CONVERSATION LOGIC (from app.py)
# ============================================================================

def _generate_summary(query: str, content: dict) -> dict:
    """Generate summaries of RAG, Web, and Meetings content"""
    summaries = {}
    
    if content.get("rag"):
        prompt = f"""Content from course materials:
{content['rag']}

Summarize in 1-2 sentences for query: "{query}" """
        
        try:
            completion = synthesizer_client.chat.completions.create(
                model="anthropic/claude-3-5-sonnet",
                messages=[{"role": "user", "content": prompt}]
            )
            summaries["rag"] = completion.choices[0].message.content
        except Exception as e:
            print(f"Error summarizing RAG: {e}")
            summaries["rag"] = content.get("rag", "")
    
    if content.get("web"):
        prompt = f"""Content from web research:
{content['web']}

Summarize in 1-2 sentences for query: "{query}" """
        
        try:
            completion = synthesizer_client.chat.completions.create(
                model="anthropic/claude-3-5-sonnet",
                messages=[{"role": "user", "content": prompt}]
            )
            summaries["web"] = completion.choices[0].message.content
        except Exception as e:
            print(f"Error summarizing web: {e}")
            summaries["web"] = content.get("web", "")
    
    # Pass meetings data through without summarizing (already formatted)
    if content.get("meetings"):
        summaries["meetings"] = content.get("meetings", "")
    
    return summaries

def _synthesize_answer(query: str, summary: dict, meeting: dict) -> str:
    """Generate final chat response"""
    rag_part = f"From course materials: {summary.get('rag', '')}" if summary.get('rag') else ""
    web_part = f"From research: {summary.get('web', '')}" if summary.get('web') else ""
    meetings_part = f"\n\nSTUDENT'S CALENDAR:\n{summary.get('meetings', '')}" if summary.get('meetings') else ""
    
    prompt = f"""Meeting: {meeting.get('title', 'Unknown')}, {meeting.get('description', '')}
Meeting time: {meeting.get('start_time', 'N/A')}, Location: {meeting.get('location', 'N/A')}

Student Question: "{query}"

{rag_part}

{web_part}
{meetings_part}

---

Write a helpful, coherent chat response that:
1. Directly answers the student's question
2. Combines all available sources naturally
3. Is conversational (2-3 paragraphs)
4. Explains concepts clearly"""
    
    try:
        completion = synthesizer_client.chat.completions.create(
            model="anthropic/claude-3-5-sonnet",
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error synthesizing answer: {e}")
        return f"I encountered an error processing your query. Please try again."

# ============================================================================
# ROUTES - AUTHENTICATION (from main.py)
# ============================================================================

@app.get("/")
async def root():
    """Serve index.html"""
    return FileResponse("index.html")

@app.get("/auth/google")
async def auth_google(request: Request):
    """Initiate Google OAuth flow"""
    if MOCK_AUTH:
        user_data = {
            "email": "demo@example.com",
            "name": "Demo User",
            "picture": "https://via.placeholder.com/150",
            "access_token": "mock_token_12345",
            "refresh_token": "mock_refresh_token",
        }
        session_id = create_session(user_data)
        response = RedirectResponse(url="/index.html?session=" + session_id)
        response.set_cookie("session_id", session_id, httponly=True, samesite="Lax")
        return response
    
    state = generate_state()
    request.session["oauth_state"] = state
    
    scopes = " ".join([
        "openid",
        "profile",
        "email",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/drive",
    ])
    
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&state={state}"
        f"&access_type=offline"
    )
    
    response = RedirectResponse(url=google_auth_url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="Lax")
    return response

@app.post("/auth/callback")
async def auth_callback(request: Request):
    """Handle Google OAuth callback"""
    try:
        body = await request.json()
        code = body.get("code")
        
        if not code:
            raise HTTPException(status_code=400, detail="No authorization code provided")
        
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        }
        
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)
            token_response.raise_for_status()
            tokens = token_response.json()
        
        access_token = tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")
        
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_response.raise_for_status()
            user_info = user_response.json()
        
        user_data = {
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "picture": user_info.get("picture"),
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token"),
        }
        
        session_id = create_session(user_data)
        
        response = RedirectResponse(url="/index.html?session=" + session_id)
        response.set_cookie("session_id", session_id, httponly=True, samesite="Lax")
        return response
        
    except httpx.HTTPError as e:
        print(f"HTTP error during auth callback: {e}")
        raise HTTPException(status_code=400, detail="OAuth token exchange failed")
    except Exception as e:
        print(f"Error in auth callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/logout")
async def logout(request: Request):
    """Logout and clear session"""
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(session_id)
    
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("session_id")
    return response

@app.get("/api/user")
async def get_user(request: Request):
    """Get current user info"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_session = get_session(session_id)
    if not user_session:
        raise HTTPException(status_code=401, detail="Session expired")
    
    user_data = user_session.get("user", {})
    return {
        "email": user_data.get("email"),
        "name": user_data.get("name"),
        "picture": user_data.get("picture"),
    }

# ============================================================================
# ROUTES - MEETING & CHAT (combined from app.py + main.py)
# ============================================================================

@app.post("/api/prep-meeting")
async def prep_meeting(request: Request):
    """
    Initialize meeting session
    Can work with mock meetings or custom meeting data
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_session = get_session(session_id)
    if not user_session:
        raise HTTPException(status_code=401, detail="Session expired")
    
    data = await request.json()
    
    # Determine meeting data and keep full meetings list accessible
    if data.get('meetings') and 'mock_index' in data:
        meeting_data = MOCK_MEETINGS[data.get('mock_index', 0)]
        meetings_list = MOCK_MEETINGS
    else:
        meeting_data = data.get('meeting_data', {})
        # Normalize to list: if user provided array, use it, otherwise wrap single meeting
        if isinstance(data.get('meeting_data'), list):
            meetings_list = data.get('meeting_data')
        else:
            meetings_list = [meeting_data]

    # Create meeting session ID
    meeting_session_id = f"meeting_{secrets.token_hex(8)}"

    # Store meeting in user session (include full list under all_meetings)
    user_session['meetings'][meeting_session_id] = {
        "data": meeting_data,
        "all_meetings": meetings_list,
        "created_at": datetime.now().isoformat()
    }
    user_session['conversation_history'][meeting_session_id] = []
    
    return {
        "session_id": session_id,
        "meeting_session_id": meeting_session_id,
        "status": "ready",
        "meeting": meeting_data,
        "all_meetings": meetings_list
    }


# --- RAG endpoints (formerly in main.py) ---
@app.on_event("startup")
def rag_startup():
    # Build index at startup and start file monitor in background
    try:
        build_or_rebuild_index()
    except Exception as e:
        logging.error(f"Error building index on startup: {e}")

    monitor_thread = Thread(target=start_file_monitor, daemon=True)
    monitor_thread.start()


@app.post("/api/search")
async def search_local_context(request: SearchRequest):
    try:
        search_query = request.meeting_name
        if request.meeting_description:
            search_query += f" - {request.meeting_description}"

        logging.info(f"Loading index for query: '{search_query}'")
        storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
        Settings.embed_model = embed_model
        index = load_index_from_storage(storage_context)

        retriever = index.as_retriever(similarity_top_k=3)
        retrieved_nodes = retriever.retrieve(search_query)

        SIMILARITY_THRESHOLD = 0.7
        if not retrieved_nodes or retrieved_nodes[0].score < SIMILARITY_THRESHOLD:
            logging.warning("No relevant context found in local files for the query.")
            return {
                "query": search_query,
                "answer": "",
                "source": "local_rag_empty"
            }

        context_for_llm = "\n\n---\n\n".join([node.get_content() for node in retrieved_nodes])
        source_files = sorted(list({node.metadata.get('file_name', 'Unknown') for node in retrieved_nodes}))
        logging.info(f"Found relevant context from chunks in files: {source_files}")

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
async def search_local_context_get():
    return {"detail": "Use POST /api/search with JSON body: {\n  \"meeting_name\": \"...\",\n  \"meeting_description\": \"optional\"\n}\n"}


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(status_code=204, content=None)

@app.post("/api/chat")
async def chat(request: Request):
    """
    Main chat endpoint
    
    Flow:
    1. Receive query
    2. Fetch from RAG + Web
    3. Synthesize answer with LLM
    4. Generate audio
    5. Store in history
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_session = get_session(session_id)
    if not user_session:
        raise HTTPException(status_code=401, detail="Session expired")
    
    data = await request.json()
    meeting_session_id = data.get('meeting_session_id')
    query = data.get('query') or data.get('text', '')
    
    if not meeting_session_id or meeting_session_id not in user_session['meetings']:
        raise HTTPException(status_code=400, detail="Invalid meeting session")
    
    if not query:
        raise HTTPException(status_code=400, detail="No query provided")
    
    meeting_data = user_session['meetings'][meeting_session_id]['data']
    history = user_session['conversation_history'][meeting_session_id]
    
    # ─── STEP 1: Fetch content ───
    content = fetcher_agent.fetch_all(query, meeting_data)
    
    # ─── STEP 2: Get decision ───
    decision = decision_agent.analyze_and_decide(query, meeting_data, history)
    
    # ─── STEP 3: Generate summary ───
    summary = _generate_summary(query, content)
    
    # ─── STEP 4: Synthesize answer ───
    final_answer = _synthesize_answer(query, summary, meeting_data)
    
    # ─── STEP 5: Generate audio ───
    audio_url = await generate_audio_with_elevenlabs(final_answer)
    
    # ─── STEP 6: Store in history ───
    history.append({
        "query": query,
        "answer": final_answer,
        "decision": decision.get('decision'),
        "timestamp": datetime.now().isoformat()
    })
    
    # ─── STEP 7: Return response ───
    return {
        "session_id": session_id,
        "meeting_session_id": meeting_session_id,
        "query": query,
        "text": final_answer,
        "answer": final_answer,  # Support both field names
        "audio_url": audio_url,
        "sources": {
            "rag": content.get("rag", ""),
            "web": content.get("web", "")
        },
        "decision": decision.get('decision'),
        "reasoning": decision.get('reasoning'),
        "source": "private_docs"
    }

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok"}

# ============================================================================
# STATIC FILES & SPA ROUTING
# ============================================================================

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve index.html for SPA routing"""
    if (full_path.startswith("api/") or 
        full_path.startswith("auth/") or 
        full_path.startswith("static/") or 
        full_path.endswith(".json") or
        full_path == "favicon.ico"):
        raise HTTPException(status_code=404, detail="Not Found")
    
    return FileResponse("index.html")

# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    mode = "🎭 MOCK MODE" if MOCK_AUTH else "🔐 REAL OAuth MODE"
    print(f"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║      Calendar-Genie Unified Backend                          ║
    ║      {mode}
    ╠═══════════════════════════════════════════════════════════════╣
    ║ Frontend: http://localhost:8000/index.html                   ║
    ║ API: http://localhost:8000/api/chat                          ║
    ║ Health: http://localhost:8000/health                         ║
    ║                                                               ║
    ║ Features:                                                     ║
    ║ ✓ Google OAuth + Session Management                          ║
    ║ ✓ LLM-powered Chat with RAG/Web Search                       ║
    ║ ✓ ElevenLabs Audio Generation                                ║
    ║ ✓ Conversation History Tracking                              ║
    ║                                                               ║
    ║ To use REAL OAuth, set:                                      ║
    ║   export GOOGLE_CLIENT_ID="your-client-id"                  ║
    ║   export GOOGLE_CLIENT_SECRET="your-client-secret"          ║
    ║                                                               ║
    ║ To use MOCK MODE, set:                                       ║
    ║   export MOCK_AUTH=true                                      ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000)
