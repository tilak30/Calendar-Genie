# Calendar-Genie Backend - Architecture

## Overview

This unified backend combines:
- **UI Session Management** (from main.py) - FastAPI with Google OAuth
- **LLM Conversation Logic** (from app.py) - Intelligent chat with RAG/Web search
- **Audio Generation** - ElevenLabs text-to-speech integration

## Why FastAPI?

✅ **Advantages over Flask:**
- Async/await support (better for I/O-bound operations like API calls)
- Built-in request validation with Pydantic
- Automatic OpenAPI documentation
- Better performance
- Native support for streaming responses
- Type hints throughout

## Architecture

```
server.py (8000)
├── Authentication Routes (/auth/*)
│   ├── Google OAuth login/callback
│   └── Session management
├── API Routes (/api/*)
│   ├── /prep-meeting - Initialize meeting session
│   ├── /chat - LLM conversation with agents
│   ├── /user - Get user info
│   └── /logout - Clear session
├── Health Check (/health)
└── SPA Routing (serves index.html)

Agents (from agents/)
├── conversation_agent.py - Decides what to fetch (theory/practice/both)
├── smart_fetcher.py - Fetches from RAG/Web
└── answer_synthesizer.py - (optional) Alternative synthesizer

External APIs
├── OpenRouter (Anthropic Claude) - LLM responses
├── ElevenLabs - Audio generation
├── Google Calendar API - Calendar access
└── Tavily/Web Search - External research
```

## Session Structure

```javascript
sessions[session_id] = {
  user: {
    email: "user@example.com",
    name: "User Name",
    picture: "...",
    access_token: "...",
    refresh_token: "..."
  },
  meetings: {
    meeting_session_id: {
      data: { title, description, ...meeting info },
      created_at: "2025-11-15T..."
    }
  },
  conversation_history: {
    meeting_session_id: [
      {
        query: "...",
        answer: "...",
        decision: "rag|web|hybrid",
        timestamp: "..."
      }
    ]
  }
}
```

## API Endpoints

### Authentication
- `GET /auth/google` - Initiate OAuth flow
- `POST /auth/callback` - OAuth callback handler
- `POST /auth/logout` - Logout
- `GET /api/user` - Get current user

### Meetings & Chat
- `POST /api/prep-meeting` - Create meeting session
  ```json
  {
    "meetings": true,
    "mock_index": 0
  }
  ```
  Returns: `{ session_id, meeting_session_id, status, meeting }`

- `POST /api/chat` - Send query and get response with audio
  ```json
  {
    "meeting_session_id": "...",
    "query": "What's my next meeting?"
  }
  ```
  Returns: `{ text, audio_url, sources, decision, reasoning }`

### Health
- `GET /health` - Server status

## Running the Server

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MOCK_AUTH=true
export GOOGLE_CLIENT_ID="your-id"
export GOOGLE_CLIENT_SECRET="your-secret"
export OPENROUTER_API_KEY="your-key"
export ELEVENLABS_API_KEY="your-key"

# Run the server
python server.py

# Server runs on http://localhost:8000
```

## Migration from Flask/FastAPI

### Old Flow
- `main.py`: OAuth + session creation
- `app.py`: Meeting prep + chat on port 5001
- Two separate servers, potential conflicts

### New Flow
- `server.py`: Everything in one FastAPI server
- Single port (8000)
- Unified session management
- Async operations throughout

## Key Implementation Details

### Session Management
- Uses Starlette SessionMiddleware for cookie-based CSRF protection
- In-memory storage (upgrade to Redis/DB for production)
- Per-user meeting sessions for multi-meeting support

### LLM Flow
1. **Fetch**: SmartFetcherAgent retrieves from RAG + Web
2. **Decide**: ConversationAnalysisAgent determines best sources
3. **Summarize**: Claude summarizes fetched content
4. **Synthesize**: Claude generates coherent response
5. **Audio**: ElevenLabs converts text to speech
6. **History**: Store in conversation history for context

### Error Handling
- Missing API keys default gracefully (audio_url = null)
- Fallback content in agents when external services unavailable
- Proper HTTP status codes and error messages

## Frontend Integration

The frontend should:
1. Redirect to `/auth/google` for login
2. Extract `session_id` from URL query params
3. Store `session_id` in localStorage/cookies
4. Include `session_id` in cookie for authenticated requests
5. Call `/api/prep-meeting` first to get `meeting_session_id`
6. Use `meeting_session_id` for all chat requests

## Production Checklist

- [ ] Move sessions from memory to database (MongoDB/PostgreSQL)
- [ ] Replace in-memory storage with Redis cache
- [ ] Add proper logging/monitoring
- [ ] Implement rate limiting on /api/chat
- [ ] Add request timeout handling
- [ ] Implement conversation history persistence
- [ ] Add user preference storage (voice settings, etc.)
- [ ] Implement proper secrets management (use environment files or secrets vault)
- [ ] Add authentication token refresh for Google OAuth
- [ ] Set up proper SSL/TLS certificates
- [ ] Configure CORS for production domains
