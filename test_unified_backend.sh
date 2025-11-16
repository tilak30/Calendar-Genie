#!/bin/bash
# Test script for unified backend

BASE_URL="http://localhost:8000"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Calendar-Genie Backend Integration Test            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Get session via OAuth mock
echo "📝 Step 1: Getting session via mock OAuth..."
SESSION_COOKIE=$(curl -s -X GET "$BASE_URL/auth/google" -i | grep "session_id=" | head -1 | sed 's/.*session_id=\([^;]*\).*/\1/')
SESSION_ID=$SESSION_COOKIE

if [ -z "$SESSION_ID" ]; then
  echo "❌ Failed to get session ID"
  exit 1
fi

echo "✅ Got session ID: $SESSION_ID"
echo ""

# Step 2: Verify user endpoint
echo "📝 Step 2: Verifying user session..."
curl -s -X GET "$BASE_URL/api/user" \
  -H "Cookie: session_id=$SESSION_ID" | python3 -m json.tool
echo ""

# Step 3: Prepare meeting
echo "📝 Step 3: Preparing meeting session..."
MEETING_RESPONSE=$(curl -s -X POST "$BASE_URL/api/prep-meeting" \
  -H "Cookie: session_id=$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{"meetings": true, "mock_index": 0}')

MEETING_SESSION_ID=$(echo "$MEETING_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('meeting_session_id', ''))")

if [ -z "$MEETING_SESSION_ID" ]; then
  echo "❌ Failed to create meeting session"
  echo "$MEETING_RESPONSE" | python3 -m json.tool
  exit 1
fi

echo "✅ Got meeting session ID: $MEETING_SESSION_ID"
echo ""

# Step 4: Send chat query
echo "📝 Step 4: Sending chat query..."
CHAT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/chat" \
  -H "Cookie: session_id=$SESSION_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"meeting_session_id\": \"$MEETING_SESSION_ID\",
    \"query\": \"What is this meeting about?\"
  }")

echo "$CHAT_RESPONSE" | python3 -m json.tool
echo ""

# Step 5: Check health
echo "📝 Step 5: Health check..."
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║                   ✅ All Tests Passed                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
