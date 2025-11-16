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

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

def _load_mock_meetings() -> list:
    try:
        with open('meeting.json', 'r') as f:
            data = json.load(f)
            return data.get('meetings', [])
    except Exception:
        return []

# Load mock meetings (initial)
MOCK_MEETINGS = _load_mock_meetings()

# ============================================================================
# IMPORTS - Agent Classes
# ============================================================================
from agents.conversation_agent import ConversationAnalysisAgent
from agents.smart_fetcher import SmartFetcherAgent
from agents.scheduler_agent import SchedulerAgent
from openai import OpenAI

# Initialize agents
decision_agent = ConversationAnalysisAgent()
fetcher_agent = SmartFetcherAgent()
scheduler_agent = SchedulerAgent()

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

def _synthesize_answer(query: str, summary: dict, meeting: dict, history: List[Dict], all_meetings: List[Dict]) -> str:
    """Generate final chat response, including recent conversation history so the LLM can refer back.

    history: list of dicts with keys 'query' and 'answer'
    """
    rag_part = f"From course materials: {summary.get('rag', '')}" if summary.get('rag') else ""
    web_part = f"From research: {summary.get('web', '')}" if summary.get('web') else ""
    meetings_part = f"\n\nSTUDENT'S CALENDAR:\n{summary.get('meetings', '')}" if summary.get('meetings') else ""

    # Build conversation history text (last 8 turns)
    history_text = "No prior conversation."
    try:
        if history:
            lines = []
            recent = history[-8:]
            for i, turn in enumerate(recent):
                q = turn.get('query', '')
                a = turn.get('answer', '')
                lines.append(f"User: {q}")
                lines.append(f"Assistant: {a}")
            history_text = "\n".join(lines)
    except Exception:
        history_text = "(unable to load history)"

    # Full meetings JSON to give the model complete context
    try:
        all_meetings_json = json.dumps(all_meetings) if all_meetings else "[]"
    except Exception:
        all_meetings_json = "[]"

    # Decide response style: concise by default; detailed only if asked explicitly
    ql = (query or "").lower()
    wants_detail = any(w in ql for w in ["explain", "details", "in detail", "elaborate", "why", "how", "walk me through"])
    style_instructions = (
        "Be concise: answer in 2-4 sentences. If a list is helpful, keep it short."
        if not wants_detail else
        "Provide a thorough, detailed explanation with clear structure."
    )

    # Current local date/time context for correct tense
    try:
        now_local = datetime.now().astimezone().strftime("%b %d, %Y %I:%M %p %Z").lstrip('0')
    except Exception:
        now_local = "(unknown)"

    prompt = f"""Meeting: {meeting.get('title', 'Unknown')}, {meeting.get('description', '')}
Meeting time: {meeting.get('start_time', 'N/A')}, Location: {meeting.get('location', 'N/A')}

RECENT CONVERSATION:
{history_text}

Student Question: "{query}"

{rag_part}

{web_part}
{meetings_part}

ALL MEETINGS (full JSON from meeting.json):
{all_meetings_json}

---

Write a helpful, coherent chat response that:
1. Directly answers the student's question
2. References earlier conversation when relevant
3. Combines all available sources naturally
4. {style_instructions}
5. Use correct tense based on time. Current local date/time is: {now_local}.
   - Use past tense when referring to meetings that have already ended.
   - Use present progressive for meetings happening right now.
   - Use future tense for upcoming meetings.
6. If the user asks a follow-up, clarify what was asked before you change the topic."""

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
        # Fresh-load meetings from disk so updates in meeting.json are picked up without restart
        latest_meetings = _load_mock_meetings()
        idx = data.get('mock_index', 0)
        if not latest_meetings:
            latest_meetings = MOCK_MEETINGS
        if not latest_meetings:
            raise HTTPException(status_code=400, detail="No meetings available")
        if idx < 0 or idx >= len(latest_meetings):
            idx = 0
        meeting_data = latest_meetings[idx]
        meetings_list = latest_meetings
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


@app.get("/api/meetings")
async def get_all_meetings(request: Request):
    """Return the full list of meetings (all fields).

    - In MOCK mode this returns the contents of `meeting.json`.
    - In real mode this requires an authenticated session and returns the meetings
      stored for that session (if any), otherwise falls back to the disk file.
    This endpoint intentionally takes no parameters and returns the full meeting objects.
    """
    # If in mock mode, return the latest meetings from disk (no restart required)
    if MOCK_AUTH:
        latest = _load_mock_meetings()
        return {"meetings": latest if latest else MOCK_MEETINGS}

    # Otherwise require a valid session
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_session = get_session(session_id)
    if not user_session:
        raise HTTPException(status_code=401, detail="Session expired")

    # Collect meetings stored in the user's session
    collected = []
    for m in user_session.get('meetings', {}).values():
        # Each stored meeting may include 'data' and/or 'all_meetings'
        if isinstance(m.get('all_meetings'), list) and m.get('all_meetings'):
            collected.extend(m.get('all_meetings'))
        elif m.get('data'):
            collected.append(m.get('data'))

    # Fallback to disk if nothing in session
    if not collected:
        try:
            with open('meeting.json','r') as f:
                collected = json.load(f).get('meetings', [])
        except Exception:
            collected = MOCK_MEETINGS

    return {"meetings": collected}

@app.post("/api/reload-meetings")
async def reload_meetings():
    """Reload meetings from meeting.json into memory and return count.

    Useful in mock mode to reflect updates without restarting the server.
    """
    global MOCK_MEETINGS
    latest = _load_mock_meetings()
    if latest:
        MOCK_MEETINGS = latest
    return {"reloaded": True, "count": len(MOCK_MEETINGS)}

@app.post("/api/chat")
async def chat(request: Request):
    """
    Main chat endpoint
    
    Flow:
    1. Receive query
    2. Check if it's a scheduling request (SchedulerAgent)
    3. If scheduling: handle via scheduler agent
    4. Else: fetch from RAG + Web + Meetings
    5. Synthesize answer with LLM
    6. Generate audio
    7. Store in history
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
    all_meetings = user_session['meetings'][meeting_session_id].get('all_meetings', [])
    
    # ─── CHECK FOR SCHEDULING INTENT ───
    # Handle follow-ups first (e.g., replacement flow)
    followup = scheduler_agent.process_followup(query, {
        "current_meeting": meeting_data,
        "user": user_session.get("user", {})
    }) if hasattr(scheduler_agent, 'process_followup') else None
    if followup:
        history.append({
            "query": query,
            "answer": followup.get("message", ""),
            "decision": "scheduling",
            "timestamp": datetime.now().isoformat()
        })
        return {
            "session_id": session_id,
            "meeting_session_id": meeting_session_id,
            "query": query,
            "answer": followup.get("message", ""),
            "text": followup.get("message", ""),
            "audio_url": await generate_audio_with_elevenlabs(followup.get("message", "")),
            "sources": {"rag": "", "web": "", "meetings": ""},
            "meetings_structured": [],
            "decision": "scheduling",
            "reasoning": "Handling schedule follow-up",
            "source": "scheduler_agent",
            "scheduler_action": followup.get("action"),
            "scheduler_details": followup.get("details"),
            "needs_confirmation": followup.get("needs_confirmation", False),
            "agent_trace": followup.get("trace")
        }

    # First check if user is confirming a pending schedule
    if scheduler_agent.pending_confirmation:
        result = scheduler_agent.confirm_and_schedule(query)
        if result["action"] in ["scheduled", "cancelled"]:
            # Store in history
            history.append({
                "query": query,
                "answer": result["message"],
                "decision": "scheduling",
                "timestamp": datetime.now().isoformat()
            })
            
            # Reload meetings if successfully scheduled
            if result["action"] == "scheduled":
                try:
                    with open('meeting.json', 'r') as f:
                        updated_meetings = json.load(f).get('meetings', [])
                        user_session['meetings'][meeting_session_id]['all_meetings'] = updated_meetings
                except Exception:
                    pass
            
            return {
                "session_id": session_id,
                "meeting_session_id": meeting_session_id,
                "query": query,
                "answer": result["message"],
                "text": result["message"],
                "audio_url": await generate_audio_with_elevenlabs(result["message"]),
                "sources": {"rag": "", "web": "", "meetings": ""},
                "meetings_structured": [],
                "decision": "scheduling",
                "reasoning": "Confirming scheduled meeting",
                "source": "scheduler_agent",
                "scheduler_action": result["action"],
                "agent_trace": result.get("trace")
            }
    
    # Check if this is a new scheduling request
    scheduling_result = scheduler_agent.handle_scheduling_request(query, {
        "current_meeting": meeting_data,
        "user": user_session.get("user", {})
    })
    
    if scheduling_result["action"] != "not_scheduling":
        # This is a scheduling request
        history.append({
            "query": query,
            "answer": scheduling_result["message"],
            "decision": "scheduling",
            "timestamp": datetime.now().isoformat()
        })
        
        return {
            "session_id": session_id,
            "meeting_session_id": meeting_session_id,
            "query": query,
            "answer": scheduling_result["message"],
            "text": scheduling_result["message"],
            "audio_url": await generate_audio_with_elevenlabs(scheduling_result["message"]),
            "sources": {"rag": "", "web": "", "meetings": ""},
            "meetings_structured": [],
            "decision": "scheduling",
            "reasoning": "Handling schedule request",
            "source": "scheduler_agent",
            "scheduler_action": scheduling_result["action"],
            "scheduler_details": scheduling_result.get("details"),
            "needs_confirmation": scheduling_result.get("needs_confirmation", False),
            "agent_trace": scheduling_result.get("trace")
        }
    
    # ─── NORMAL CHAT FLOW (not scheduling) ───
    # STEP 1: Fetch content ───
    content = fetcher_agent.fetch_all(query, meeting_data)
    
    # ─── STEP 2: Get decision ───
    decision = decision_agent.analyze_and_decide(query, meeting_data, history)
    
    # ─── STEP 3: Generate summary ───
    summary = _generate_summary(query, content)
    
    # ─── STEP 4: Synthesize answer (include history for context) ───
    final_answer = _synthesize_answer(query, summary, meeting_data, history, all_meetings)
    
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
            "web": content.get("web", ""),
            "meetings": content.get("meetings", "")
        },
        "meetings_structured": content.get("meetings_structured", []),
        "decision": decision.get('decision'),
        "reasoning": decision.get('reasoning'),
        "source": "private_docs",
        "agent_trace": fetcher_agent.get_execution_summary() if hasattr(fetcher_agent, 'get_execution_summary') else None
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
