# Frontend Integration - API Changes

## Breaking Changes from Old Code

### 1. Port Changed
- **Old**: main.py on 8000, app.py on 5001
- **New**: server.py on 8000 only
- **Action**: Update all API URLs to use port 8000

### 2. Session ID Handling

#### Old Flow (Flask app.py)
```javascript
// No OAuth, just pass session_id directly
const response = await fetch('http://localhost:5001/api/prep-meeting', {
  method: 'POST',
  body: JSON.stringify({
    meetings: true,
    mock_index: 0
  })
});
const {session_id} = await response.json();

// Use session_id in chat
await fetch('http://localhost:5001/api/chat', {
  method: 'POST',
  body: JSON.stringify({
    session_id,  // This field
    query: "..."
  })
});
```

#### New Flow (FastAPI server.py)
```javascript
// 1. First, authenticate via OAuth
window.location.href = 'http://localhost:8000/auth/google';
// Will redirect back with session_id in URL

// 2. Extract session_id from URL
const urlParams = new URLSearchParams(window.location.search);
const sessionId = urlParams.get('session');

// 3. Prepare meeting to get meeting_session_id
const response = await fetch('http://localhost:8000/api/prep-meeting', {
  method: 'POST',
  credentials: 'include',  // IMPORTANT: Send cookies
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    meetings: true,
    mock_index: 0
  })
});
const {meeting_session_id} = await response.json();  // NEW field

// 4. Use meeting_session_id (not session_id) in chat
await fetch('http://localhost:8000/api/chat', {
  method: 'POST',
  credentials: 'include',  // IMPORTANT: Send cookies
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    meeting_session_id,  // NEW field (not session_id)
    query: "..."
  })
});
```

### 3. Request Structure Changes

#### Prep Meeting Request
```javascript
// OLD (app.py)
{
  "meetings": true,
  "mock_index": 0
}

// NEW (server.py) - same structure but requires auth
{
  "meetings": true,
  "mock_index": 0
}
```

#### Prep Meeting Response
```javascript
// OLD (app.py)
{
  "session_id": "session_abc123",     // ← No longer used for chat
  "status": "ready",
  "meeting": {...}
}

// NEW (server.py)
{
  "session_id": "...",                // ← Authentication session
  "meeting_session_id": "meeting_...", // ← NEW: Use this for chat!
  "status": "ready",
  "meeting": {...}
}
```

#### Chat Request
```javascript
// OLD (app.py)
{
  "session_id": "session_abc123",
  "query": "What is this meeting about?"
}

// NEW (server.py)
{
  "meeting_session_id": "meeting_abc123",  // ← CHANGED from session_id
  "query": "What is this meeting about?"
}
```

#### Chat Response
```javascript
// OLD (app.py)
{
  "session_id": "...",
  "query": "...",
  "answer": "Response text",
  "sources": {"rag": "...", "web": "..."},
  "decision": "rag|web|hybrid",
  "reasoning": "..."
}

// NEW (server.py) - SUPERSET of old, with audio!
{
  "session_id": "...",
  "meeting_session_id": "...",
  "query": "...",
  "text": "Response text",           // ← NEW field name
  "answer": "Response text",       // ← KEPT for compatibility
  "audio_url": "data:audio/mpeg;base64,...",  // ← NEW!
  "sources": {"rag": "...", "web": "..."},
  "decision": "rav|web|hybrid",
  "reasoning": "...",
  "source": "private_docs"
}
```

## Migration Checklist

### For Old Flask App (app.py) Users
- [ ] Remove references to port 5001
- [ ] Update all endpoints to use port 8000
- [ ] Change `session_id` to `meeting_session_id` in chat requests
- [ ] Ensure `credentials: 'include'` in all fetch calls
- [ ] Remove manual session_id handling (use cookies)

### For Old FastAPI App (main.py) Users
- [ ] Merge functionality into server.py (already done!)
- [ ] Update frontend to extract `meeting_session_id` from prep-meeting response
- [ ] Handle new `audio_url` field in chat responses
- [ ] Add `credentials: 'include'` to fetch calls

### General Updates
- [ ] Update API URLs from localhost:5001 → localhost:8000
- [ ] Update API URLs from localhost:8000/api/chat (if using old main.py)
- [ ] Handle both `text` and `answer` fields (both present for compatibility)
- [ ] Add audio playback for `audio_url` field
- [ ] Update error handling (FastAPI uses different error codes)

## Code Examples

### Complete Working Example (Vanilla JS)

```javascript
class CalendarGenieClient {
  constructor(baseUrl = 'http://localhost:8000') {
    this.baseUrl = baseUrl;
    this.sessionId = null;
    this.meetingSessionId = null;
  }

  async login() {
    // Redirect to OAuth
    window.location.href = `${this.baseUrl}/auth/google`;
  }

  async initSession() {
    // Extract session from URL after OAuth redirect
    const urlParams = new URLSearchParams(window.location.search);
    this.sessionId = urlParams.get('session');
    
    if (!this.sessionId) {
      throw new Error('No session found. Please login first.');
    }
  }

  async prepareMeeting(mockIndex = 0) {
    const response = await fetch(`${this.baseUrl}/api/prep-meeting`, {
      method: 'POST',
      credentials: 'include',  // Send cookies
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        meetings: true,
        mock_index: mockIndex
      })
    });

    if (!response.ok) {
      throw new Error(`Failed to prepare meeting: ${response.status}`);
    }

    const data = await response.json();
    this.meetingSessionId = data.meeting_session_id;
    return data.meeting;
  }

  async sendMessage(query) {
    if (!this.meetingSessionId) {
      throw new Error('No meeting prepared. Call prepareMeeting() first.');
    }

    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST',
      credentials: 'include',  // Send cookies
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        meeting_session_id: this.meetingSessionId,
        query: query
      })
    });

    if (!response.ok) {
      throw new Error(`Chat failed: ${response.status}`);
    }

    return await response.json();
  }

  async playAudio(audioUrl) {
    if (!audioUrl) {
      console.warn('No audio URL provided');
      return;
    }

    const audio = new Audio(audioUrl);
    await audio.play();
  }
}

// Usage
const client = new CalendarGenieClient();

// 1. Login
async function handleLogin() {
  client.login();
}

// 2. After OAuth redirect, initialize
async function initializeApp() {
  await client.initSession();
  const meeting = await client.prepareMeeting(0);
  console.log('Meeting prepared:', meeting);
}

// 3. Send messages
async function handleUserMessage(userMessage) {
  const response = await client.sendMessage(userMessage);
  
  // Display response
  console.log('Response:', response.text);
  console.log('Reasoning:', response.reasoning);
  
  // Play audio if available
  if (response.audio_url) {
    await client.playAudio(response.audio_url);
  }
}
```

### React Component Example

```jsx
import { useEffect, useState } from 'react';

export function ChatInterface() {
  const [sessionId, setSessionId] = useState(null);
  const [meetingSessionId, setMeetingSessionId] = useState(null);
  const [meeting, setMeeting] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  // Initialize on mount
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const session = urlParams.get('session');
    if (session) {
      setSessionId(session);
      prepareMeeting(session);
    }
  }, []);

  async function prepareMeeting(sessionId) {
    try {
      const response = await fetch('/api/prep-meeting', {
        method: 'POST',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          meetings: true,
          mock_index: 0
        })
      });
      
      const data = await response.json();
      setMeetingSessionId(data.meeting_session_id);
      setMeeting(data.meeting);
    } catch (error) {
      console.error('Failed to prepare meeting:', error);
    }
  }

  async function handleSendMessage(userMessage) {
    if (!meetingSessionId) return;

    setLoading(true);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          meeting_session_id: meetingSessionId,
          query: userMessage
        })
      });

      const data = await response.json();
      
      // Add to messages
      setMessages(prev => [...prev, {
        role: 'user',
        content: userMessage
      }, {
        role: 'assistant',
        content: data.text,
        audio: data.audio_url,
        reasoning: data.reasoning
      }]);

      // Play audio
      if (data.audio_url) {
        const audio = new Audio(data.audio_url);
        audio.play();
      }
    } catch (error) {
      console.error('Chat error:', error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat-interface">
      {meeting && (
        <div className="meeting-info">
          <h2>{meeting.title}</h2>
          <p>{meeting.description}</p>
        </div>
      )}
      
      <div className="messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <p>{msg.content}</p>
            {msg.audio && (
              <button onClick={() => new Audio(msg.audio).play()}>
                🔊 Play Audio
              </button>
            )}
            {msg.reasoning && (
              <small className="reasoning">{msg.reasoning}</small>
            )}
          </div>
        ))}
      </div>

      <input
        type="text"
        placeholder="Ask about your meeting..."
        onKeyPress={(e) => {
          if (e.key === 'Enter') {
            handleSendMessage(e.target.value);
            e.target.value = '';
          }
        }}
        disabled={loading}
      />
    </div>
  );
}
```

## Common Issues & Solutions

### Issue: "Session expired" on /api/chat
```javascript
// ❌ Wrong
await fetch('/api/chat', {
  body: JSON.stringify({session_id: sessionId, ...})
});

// ✅ Correct
await fetch('/api/chat', {
  credentials: 'include',  // Add this!
  body: JSON.stringify({meeting_session_id: meetingId, ...})
});
```

### Issue: "Invalid meeting session"
```javascript
// ❌ Wrong - using session_id
const {session_id} = await prepResp.json();
await sendMessage({session_id, query});

// ✅ Correct - using meeting_session_id
const {meeting_session_id} = await prepResp.json();
await sendMessage({meeting_session_id, query});
```

### Issue: Audio not playing
```javascript
// ❌ Wrong
new Audio(response.audio_url).play();

// ✅ Correct - handle async
const audio = new Audio(response.audio_url);
audio.play().catch(e => console.log('Audio play denied:', e));
```

## Testing with cURL

```bash
# 1. Get session
curl -X GET http://localhost:8000/auth/google -L -i

# Extract session_id from Set-Cookie header
SESSION_ID="your-session-id-here"

# 2. Prepare meeting
curl -X POST http://localhost:8000/api/prep-meeting \
  -H "Cookie: session_id=$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{"meetings": true, "mock_index": 0}'

# Extract meeting_session_id from response
MEETING_ID="your-meeting-id-here"

# 3. Send chat message
curl -X POST http://localhost:8000/api/chat \
  -H "Cookie: session_id=$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d "{\"meeting_session_id\": \"$MEETING_ID\", \"query\": \"What is this meeting?\"}"
```

That's it! Your frontend should now work with the unified backend. 🚀
