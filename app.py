from flask import Flask, request, jsonify
import json
from dotenv import load_dotenv
from datetime import datetime
import uuid
from agents.conversation_agent import ConversationAnalysisAgent
from agents.smart_fetcher import SmartFetcherAgent
from openai import OpenAI


import os
load_dotenv()
app = Flask(__name__)

# Load mock meetings
with open('meeting.json', 'r') as f:
    MOCK_MEETINGS = json.load(f)['meetings']

# Initialize agents
decision_agent = ConversationAnalysisAgent()
fetcher_agent = SmartFetcherAgent()

# Synthesizer (Claude for final answer)
synthesizer_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

# Sessions
sessions = {}

@app.route('/api/prep-meeting', methods=['POST'])
def prep_meeting():
    """Initialize meeting session"""
    data = request.json
    session_id = f"session_{uuid.uuid4().hex[:8]}"
    
    if 'meetings' in data:
        meeting_data = MOCK_MEETINGS[data['mock_index']]
    else:
        meeting_data = data
    
    sessions[session_id] = {
        "meeting_data": meeting_data,
        "conversation_history": [],
        "all_meetings": meeting_data,
        "current_time": datetime.now().isoformat()
        
    }
    # meeting_data = meeting_data[:5] if meeting_data else {}

    
    return jsonify({
        "session_id": session_id,
        "status": "ready",
        "meeting": meeting_data
    }), 200

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Main chat endpoint
    
    Flow:
    1. Receive query
    2. Agent 1: Decide what to fetch (theory/practice/both)
    3. Agent 2: Fetch from RAG + Web
    4. Claude: Synthesize answer from both sources
    5. Return: Coherent chat response
    """
    
    data = request.json
    session_id = data.get('session_id')
    query = data.get('query')
    
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    
    session = sessions[session_id]
    meeting = session['meeting_data']
    history = session['conversation_history']
    
    # ───────────────────────────────────────────────────────
    # STEP 1: Smart Fetcher Agent decides what to fetch
    # ───────────────────────────────────────────────────────
    content = fetcher_agent.fetch_all(query, meeting)
    # Returns: {"rag": "...", "web": "..."}
    
    # ───────────────────────────────────────────────────────
    # STEP 2: Decision Agent decides source
    # ───────────────────────────────────────────────────────
    decision = decision_agent.analyze_and_decide(query, meeting, history)
    
    # ───────────────────────────────────────────────────────
    # STEP 3: Generate Summary of content
    # ───────────────────────────────────────────────────────
    summary = _generate_summary(query, content)
    # Returns: {"rag_summary": "...", "web_summary": "..."}
    
    # ───────────────────────────────────────────────────────
    # STEP 4: Claude synthesizes final chat response
    # ───────────────────────────────────────────────────────
    final_answer = _synthesize_answer(query, summary, meeting)
    
    # ───────────────────────────────────────────────────────
    # STEP 5: Store + Return
    # ───────────────────────────────────────────────────────
    response = {
        "session_id": session_id,
        "query": query,
        "answer": final_answer,
        "sources": {
            "rag": content.get("rag", ""),
            "web": content.get("web", "")
        },
        "decision": decision.get('decision'),
        "reasoning": decision.get('reasoning')
    }
    
    # Store in history
    history.append({
        "query": query,
        "answer": final_answer,
        "decision": decision.get('decision'),
        "timestamp": datetime.now().isoformat()
    })
    
    return jsonify(response), 200

def _generate_summary(query: str, content: dict) -> dict:
    """Generate summaries of RAG and Web content"""
    
    summaries = {}
    
    if content.get("rag"):
        prompt = f"""Content from course materials:
{content['rag']}

Summarize in 1-2 sentences for query: "{query}" """
        
        completion = synthesizer_client.chat.completions.create(
            model="anthropic/claude-3-5-sonnet",
            messages=[{"role": "user", "content": prompt}]
        )
        summaries["rag"] = completion.choices[0].message.content
    
    if content.get("web"):
        prompt = f"""Content from web research:
{content['web']}

Summarize in 1-2 sentences for query: "{query}" """
        
        completion = synthesizer_client.chat.completions.create(
            model="anthropic/claude-3-5-sonnet",
            messages=[{"role": "user", "content": prompt}]
        )
        summaries["web"] = completion.choices[0].message.content
    
    return summaries

def _synthesize_answer(query: str, summary: dict, meeting: dict) -> str:
    """Generate final chat response"""
    
    rag_part = f"From course materials: {summary.get('rag', '')}" if summary.get('rag') else ""
    web_part = f"From research: {summary.get('web', '')}" if summary.get('web') else ""
    print(f"Meeting info: {meeting}")
    prompt = f"""Meeting: {meeting['title']},  {meeting['description']}, meeting time: {meeting.get('time', 'N/A')}, location: {meeting.get('location', 'N/A')}

Student Question: "{query}"

{rag_part}

{web_part}

---

Write a helpful, coherent chat response that:
1. Directly answers the student's question
2. Combines both sources naturally
3. Is conversational (2-3 paragraphs)
4. Explains concepts clearly"""
    
    completion = synthesizer_client.chat.completions.create(
        model="anthropic/claude-3-5-sonnet",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return completion.choices[0].message.content

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5001)
