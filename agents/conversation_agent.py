import os
import json
from openai import OpenAI

class ConversationAnalysisAgent:
    """Agent using OpenRouter with OpenAI SDK"""
    
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.model = "anthropic/claude-3-5-sonnet"
        self.meetings = self._load_meetings()
        self.conversation_history = [] 
    
    def _load_meetings(self) -> list:
        """Load all meetings from meeting.json"""
        try:
            with open('meeting.json', 'r') as f:
                data = json.load(f)
                return data.get('meetings', [])
        except Exception as e:
            print(f"Error loading meetings: {e}")
            return []
    
    def analyze_and_decide(self, 
                          query: str,
                          meeting_data: dict,
                          conversation_history: list) -> dict:
        """Uses OpenRouter Claude via OpenAI SDK"""
        
        # Build history
        history_text = ""
        if conversation_history:
            history_text = "\n".join([
                f"Turn {i+1}: {turn['query']} → {turn['decision']}"
                for i, turn in enumerate(conversation_history[-4:])
            ])
        else:
            history_text = "No previous conversation yet"
        
        # Always provide full meetings JSON so LLM can access every field
        meetings_context = ""
        try:
            if self.meetings:
                meetings_context = "\n\nALL_MEETINGS_JSON (from meeting.json):\n" + json.dumps(self.meetings)
        except Exception:
            meetings_context = "\n\nALL_MEETINGS_JSON: []"
        
        # Build prompt
        prompt = f"""You are an intelligent meeting prep agent helping a student.

MEETING:
Title: {meeting_data['title']}
Description: {meeting_data['description']}
{meetings_context}

CONVERSATION HISTORY:
{history_text}

NEW QUESTION:
"{query}"

---

DECIDE: drive|web|hybrid|meetings|history?

- DRIVE: Internal (course notes, meeting materials)
- WEB: External (tutorials, research, general info)
- HYBRID: Both internal and external
- MEETINGS: Student's calendar/schedule data
- HISTORY: Reference previous discussion

Respond ONLY with valid JSON:
{{
    "decision": "drive|web|hybrid|meetings|history",
    "reasoning": "Why this decision (1-2 sentences)",
    "confidence": 0.0-1.0,
    "student_intent": "What the student is trying to do"
}}"""
        
        try:
            # Call OpenRouter Claude
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            # Parse response
            message = completion.choices[0].message.content
            decision = json.loads(message)
            
            # Validate
            if decision.get("decision") not in ["drive", "web", "hybrid", "meetings", "history"]:
                decision["decision"] = "hybrid"
            self.conversation_history.append({"role": "assistant", "content": message})

            return decision
            
        except json.JSONDecodeError:
            return {
                "decision": "hybrid",
                "reasoning": "Could not parse agent response, defaulting to hybrid",
                "confidence": 0.5,
                "student_intent": "Unknown"
            }
        except Exception as e:
            print(f"Agent error: {e}")
            return {
                "decision": "hybrid",
                "reasoning": f"Error: {str(e)}",
                "confidence": 0.3,
                "student_intent": "Unknown"
            }
