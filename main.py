"""
Calendar-Genie Backend
FastAPI server with Google OAuth auth flow and ElevenLabs audio generation
"""
import os
import json
import secrets
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI()

# Add SessionMiddleware for OAuth state management
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-in-production")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = "http://localhost:8000/auth/callback"

# ElevenLabs Configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Default: Rachel
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# Mock mode: set MOCK_AUTH=true to skip real Google OAuth
MOCK_AUTH = os.getenv("MOCK_AUTH", "false").lower() == "true"

# In-memory session store (replace with database in production)
sessions = {}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_state():
    """Generate a secure state token for CSRF protection"""
    return secrets.token_urlsafe(32)

def create_session(user_data):
    """Store session data and return session ID"""
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = user_data
    return session_id

def get_session(session_id):
    """Retrieve session data by ID"""
    return sessions.get(session_id)

def delete_session(session_id):
    """Delete session data"""
    if session_id in sessions:
        del sessions[session_id]

async def generate_audio_with_elevenlabs(text: str) -> str:
    """
    Generate audio using ElevenLabs API
    Returns a temporary audio URL (base64 data URL)
    
    Args:
        text: Text to convert to speech
        
    Returns:
        Audio URL that can be played by the frontend
        
    Raises:
        HTTPException: If ElevenLabs API fails
    """
    if not ELEVENLABS_API_KEY:
        # In test/demo mode without API key, return None instead of raising
        return None
    
    try:
        # Call ElevenLabs API to generate speech
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
            
            # ElevenLabs returns audio bytes
            audio_bytes = response.content
            
            # Convert to data URL (in production, consider S3 or streaming)
            import base64
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            audio_url = f"data:audio/mpeg;base64,{audio_b64}"
            
            return audio_url
            
    except httpx.HTTPError as e:
        # Log error but don't crash—return None and let frontend handle it
        print(f"⚠️  ElevenLabs unavailable: {str(e)}")
        return None
    except Exception as e:
        print(f"⚠️  Audio generation error: {e}")
        return None

@app.get("/")
async def root():
    """Serve index.html"""
    return FileResponse("index.html")

@app.get("/auth/google")
async def auth_google(request: Request):
    """
    Initiate Google OAuth flow.
    Redirects user to Google consent screen requesting Calendar and Drive access.
    In mock mode, directly creates a session.
    """
    if MOCK_AUTH:
        # Mock mode: create a fake user session directly
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
    
    # Real OAuth mode
    state = generate_state()
    # Store state in session for CSRF protection
    request.session["oauth_state"] = state
    
    # Request scopes for Calendar, Drive, and User info
    scopes = " ".join([
        "openid",
        "profile",
        "email",
        "https://www.googleapis.com/auth/calendar",  # Access to Google Calendar
        "https://www.googleapis.com/auth/drive",     # Access to Google Drive
    ])
    
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&state={state}"
        f"&access_type=offline"  # Request refresh token
    )
    
    response = RedirectResponse(url=google_auth_url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="Lax")
    return response

@app.post("/auth/callback")
async def auth_callback(request: Request):
    """
    Handle Google OAuth callback.
    Exchange authorization code for access token.
    """
    try:
        body = await request.json()
        code = body.get("code")
        
        if not code:
            raise HTTPException(status_code=400, detail="No authorization code provided")
        
        # Exchange code for tokens
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
        id_token = tokens.get("id_token")
        
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")
        
        # Get user info from Google
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_response.raise_for_status()
            user_info = user_response.json()
        
        # Create session with user data and tokens
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
    """Get current user info from session"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = get_session(session_id)
    if not user_data:
        raise HTTPException(status_code=401, detail="Session expired")
    
    return {
        "email": user_data.get("email"),
        "name": user_data.get("name"),
        "picture": user_data.get("picture"),
    }

@app.post("/api/chat")
async def chat(request: Request):
    """
    Chat endpoint: Receives a user query and returns a response with ElevenLabs audio.
    
    Response:
        {
            "text": "response text",
            "audio_url": "data:audio/mpeg;base64,...",
            "source": "private_docs|public_web|demo"
        }
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = get_session(session_id)
    if not user_data:
        raise HTTPException(status_code=401, detail="Session expired")
    
    try:
        body = await request.json()
        user_query = body.get("text", "")
        
        if not user_query:
            raise HTTPException(status_code=400, detail="No text provided")
        
        if MOCK_AUTH:
            # Mock mode: return demo responses with ElevenLabs audio
            demo_responses = {
                "prep me": "Great! Your next meeting is with Sarah Chen from Marketing at 2 PM today. You'll discuss Q4 campaign results. I found a recent memo about the campaign in your Drive: Q4 Marketing Summary shows strong engagement metrics.",
                "default": f"Demo response to your query: '{user_query}'. In production, this would pull from your calendar and documents using the Orchestrator flow.",
            }
            
            response_text = demo_responses.get(user_query.lower(), demo_responses["default"])
            audio_url = await generate_audio_with_elevenlabs(response_text)
            
            return {
                "text": response_text,
                "audio_url": audio_url,
                "source": "private_docs",
            }
        
        # Real mode: Implement the Orchestrator flow (Phase 3-4)
        response_text = f"Real response to your query: '{user_query}'. Backend integration coming soon!"
        audio_url = await generate_audio_with_elevenlabs(response_text)
        
        return {
            "text": response_text,
            "audio_url": audio_url,
            "source": "demo",
        }
        
    except Exception as e:
        print(f"Error in /api/chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Catch-all: serve index.html for SPA routing
@app.get("/{full_path:path}")
async def serve_index(full_path: str):
    """Serve index.html for SPA routing (including root path)"""
    # Don't intercept API routes, static files, auth routes, or favicon
    if (full_path.startswith("api/") or 
        full_path.startswith("auth/") or 
        full_path.startswith("static/") or 
        full_path.endswith(".json") or
        full_path == "favicon.ico"):
        raise HTTPException(status_code=404, detail="Not Found")
    
    # Serve index.html for "/" and all other SPA routes
    return FileResponse("index.html")

if __name__ == "__main__":
    mode = "🎭 MOCK MODE" if MOCK_AUTH else "🔐 REAL OAuth MODE"
    print(f"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║         Calendar-Genie Backend Starting                       ║
    ║         {mode}
    ╠═══════════════════════════════════════════════════════════════╣
    ║ Frontend: http://localhost:8000/index.html                   ║
    ║ API: http://localhost:8000/api/chat                          ║
    ║                                                               ║
    ║ To use REAL OAuth, set environment variables:                ║
    ║   export GOOGLE_CLIENT_ID="your-client-id"                  ║
    ║   export GOOGLE_CLIENT_SECRET="your-client-secret"          ║
    ║                                                               ║
    ║ To use MOCK MODE, set:                                       ║
    ║   export MOCK_AUTH=true                                      ║
    ║                                                               ║
    ║ Get credentials from: https://console.cloud.google.com/     ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000)
