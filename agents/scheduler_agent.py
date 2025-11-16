import os
import json
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from openai import OpenAI
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env if present
load_dotenv()

class SchedulerAgent:
    """
    Agentic Meeting Scheduler with multi-step reasoning:
    
    Phase 1: ANALYZE - Parse user request for scheduling intent
    Phase 2: CHECK - Verify time slot is free
    Phase 3: GATHER - Extract/prompt for required meeting details
    Phase 4: CONFIRM - Show details and get user confirmation
    Phase 5: COMMIT - Add to meeting.json
    
    The agent handles:
    - Natural language scheduling requests
    - Intelligent detail extraction from similar meetings
    - Conflict detection
    - Interactive confirmation
    - Persistent storage
    """
    
    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        ) if api_key else None
        self.model = "anthropic/claude-3.5-sonnet"
        self.meetings_file = "meeting.json"
        
        # Agent state
        self.current_task: Optional[Dict] = None
        self.pending_confirmation: Optional[Dict] = None
        self.pending_replacement: Optional[Dict] = None
        self.execution_log: List[Dict] = []
    
    def _load_meetings(self) -> List[Dict]:
        """Load current meetings from JSON."""
        try:
            with open(self.meetings_file, 'r') as f:
                data = json.load(f)
                return data.get('meetings', [])
        except Exception as e:
            logger.error(f"Failed to load meetings: {e}")
            return []
    
    def _save_meetings(self, meetings: List[Dict]) -> bool:
        """Save meetings back to JSON."""
        try:
            with open(self.meetings_file, 'w') as f:
                json.dump({"meetings": meetings}, f, indent=2)
            logger.info(f"Saved {len(meetings)} meetings to {self.meetings_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save meetings: {e}")
            return False
    
    def handle_scheduling_request(self, query: str, user_context: Dict) -> Dict:
        """
        Main agentic loop for scheduling.
        
        Returns:
            {
                "action": "schedule_pending" | "scheduled" | "conflict" | "need_info" | "not_scheduling",
                "message": str,
                "details": Dict (if scheduling),
                "conflicts": List[Dict] (if conflicts found),
                "needs_confirmation": bool
            }
        """
        self.execution_log = []
        
        # PHASE 1: Analyze intent
        intent = self._analyze_scheduling_intent(query, user_context)
        self.execution_log.append({"phase": "analyze", "intent": intent})
        
        if not intent.get("is_scheduling"):
            return {
                "action": "not_scheduling",
                "message": "This doesn't appear to be a scheduling request.",
                "trace": self._format_trace()
            }
        
        # Guard: if requested time is in the past, inform user
        if self._is_past_time_slot(intent.get("time_slot")):
            ts = intent.get("time_slot", {})
            start_fmt = self._format_time(ts.get("start_time", ""))
            return {
                "action": "past_time",
                "message": f"⏳ The requested time ({start_fmt}) is in the past. Please choose a future time.",
                "trace": self._format_trace()
            }
        
        # PHASE 2: Check availability
        time_slot = intent.get("time_slot")
        conflicts = self._check_conflicts(time_slot)
        self.execution_log.append({"phase": "check_conflicts", "conflicts": len(conflicts)})
        
        if conflicts:
            user_email = (user_context.get("user", {}) or {}).get("email") or "you@nyu.edu"
            any_user_is_org = False
            detailed_lines: List[str] = []
            for m in conflicts:
                # find organizer and user role
                org = next((p for p in m.get("participants", []) if p.get("is_organizer")), None)
                you = next((p for p in m.get("participants", []) if p.get("email") == user_email), None)
                user_is_org = bool(you and you.get("is_organizer"))
                any_user_is_org = any_user_is_org or user_is_org
                detailed_lines.append(
                    "- "
                    + f"{m.get('title')} ("
                    + f"{self._format_time(m.get('start_time'))} - {self._format_time(m.get('end_time'))})\n"
                    + f"  Location: {m.get('location', 'TBD')}\n"
                    + (f"  Description: {m.get('description', '')}\n" if m.get('description') else "")
                    + (f"  Organizer: {org.get('name')} <{org.get('email')}>\n" if org else "")
                )

            if any_user_is_org:
                # If the user is organizer of any conflict, be direct: not free
                return {
                    "action": "conflict",
                    "message": (
                        "⛔ This time isn't free. You're the organizer of the conflicting meeting(s):\n"
                        + "\n".join(detailed_lines)
                        + "\n\nPlease pick another time."
                    ),
                    "conflicts": conflicts,
                    "trace": self._format_trace()
                }
            else:
                # User isn't organizer; explain a bit and ask if they want to replace
                # Save context for possible replacement follow-up
                self.pending_replacement = {
                    "stage": "offer",
                    "time_slot": time_slot,
                    "mentioned": intent.get("mentioned_details", {}),
                    "conflicts": conflicts,
                    "original_query": query,
                    "user_email": user_email
                }
                return {
                    "action": "conflict",
                    "message": (
                        "⚠️ This time isn't free. Here are the conflicting meeting(s):\n"
                        + "\n".join(detailed_lines)
                        + "\nYou're not the organizer. Do you want to replace one of these with your new meeting?"
                        + "\nReply 'replace' to proceed with a replacement, or 'another time' to choose a different slot."
                    ),
                    "conflicts": conflicts,
                    "trace": self._format_trace()
                }
        
        # PHASE 3: Gather meeting details
        meeting_details = self._gather_meeting_details(query, intent, user_context)
        self.execution_log.append({"phase": "gather_details", "complete": meeting_details.get("complete", False)})
        
        if not meeting_details.get("complete"):
            return {
                "action": "need_info",
                "message": f"📝 To schedule this meeting, I need:\n{meeting_details.get('missing_info')}",
                "details": meeting_details,
                "trace": self._format_trace()
            }
        
        # PHASE 4: Prepare confirmation
        self.pending_confirmation = meeting_details
        confirmation_msg = self._format_confirmation(meeting_details)
        
        return {
            "action": "schedule_pending",
            "message": confirmation_msg + "\n\n✅ Reply 'yes' or 'confirm' to add this meeting.",
            "details": meeting_details,
            "needs_confirmation": True,
            "trace": self._format_trace()
        }
    
    def confirm_and_schedule(self, confirmation: str) -> Dict:
        """
        PHASE 5: Commit the meeting after user confirmation.
        """
        if not self.pending_confirmation:
            return {
                "action": "error",
                "message": "❌ No pending meeting to confirm."
            }
        
        # Check confirmation
        conf_lower = confirmation.lower().strip()
        if conf_lower not in ["yes", "confirm", "ok", "sure", "schedule it", "add it"]:
            self.pending_confirmation = None
            return {
                "action": "cancelled",
                "message": "❌ Meeting scheduling cancelled."
            }
        
        # Add to meeting.json (with optional replacement)
        meetings = self._load_meetings()
        new_meeting = self.pending_confirmation
        replace_id = new_meeting.pop("replace_meeting_id", None)
        replace_title = new_meeting.pop("replace_title", None)
        if replace_id:
            meetings = [m for m in meetings if m.get("meeting_id") != replace_id]
        meetings.append(new_meeting)
        
        if self._save_meetings(meetings):
            self.execution_log.append({"phase": "commit", "success": True})
            replaced_note = (
                f" (Replaced '{replace_title}')" if replace_id and replace_title else ""
            )
            result = {
                "action": "scheduled",
                "message": f"✅ Meeting '{new_meeting['title']}' scheduled successfully{replaced_note}!\n\n"
                          f"📅 {self._format_time(new_meeting['start_time'])} - {self._format_time(new_meeting['end_time'])}\n"
                          f"📍 {new_meeting['location']}",
                "meeting": new_meeting,
                "trace": self._format_trace()
            }
            self.pending_confirmation = None
            return result
        else:
            return {
                "action": "error",
                "message": "❌ Failed to save meeting to file."
            }
    
    def _analyze_scheduling_intent(self, query: str, context: Dict) -> Dict:
        """Phase 1: Use LLM to determine if this is a scheduling request and extract time."""
        
        prompt = f"""Analyze if this is a meeting scheduling request.

User Query: "{query}"
Current Date/Time: {datetime.now().strftime("%B %d, %Y %I:%M %p")}

Determine:
1. Is this a scheduling request? (book, schedule, add meeting, set up, arrange, etc.)
2. If yes, extract:
   - Requested date/time (convert to ISO format with timezone)
   - Duration (if mentioned, else default 1 hour)
   - Meeting title/topic (if mentioned)
   - Any other details

Respond with JSON only:
{{
  "is_scheduling": true/false,
  "time_slot": {{
    "start_time": "2025-11-19T08:00:00Z",
    "end_time": "2025-11-19T09:00:00Z"
  }},
  "mentioned_details": {{
    "title": "...",
    "description": "...",
    "location": "...",
    "participants": [...]
  }},
  "reasoning": "..."
}}"""
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            result = json.loads(completion.choices[0].message.content)
            return result
        except Exception as e:
            logger.error(f"Intent analysis failed: {e}")
            return {"is_scheduling": False, "reasoning": f"Parse error: {e}"}
    
    def _check_conflicts(self, time_slot: Dict) -> List[Dict]:
        """Phase 2: Check if the requested time slot conflicts with existing meetings."""
        if not time_slot:
            return []
        
        meetings = self._load_meetings()
        conflicts = []
        
        try:
            req_start = datetime.fromisoformat(time_slot["start_time"].replace('Z', '+00:00'))
            req_end = datetime.fromisoformat(time_slot["end_time"].replace('Z', '+00:00'))
            
            for meeting in meetings:
                m_start = datetime.fromisoformat(meeting["start_time"].replace('Z', '+00:00'))
                m_end = datetime.fromisoformat(meeting["end_time"].replace('Z', '+00:00'))
                
                # Check overlap
                if (req_start < m_end) and (req_end > m_start):
                    conflicts.append(meeting)
        except Exception as e:
            logger.error(f"Conflict check failed: {e}")
        
        return conflicts
    
    def _gather_meeting_details(self, query: str, intent: Dict, context: Dict) -> Dict:
        """Phase 3: Gather all required meeting details, using LLM to infer from context."""
        
        # Get similar meeting as template
        meetings = self._load_meetings()
        template_meeting = meetings[0] if meetings else None
        
        mentioned = intent.get("mentioned_details", {})
        time_slot = intent.get("time_slot", {})
        
        # Required fields
        required = ["meeting_id", "title", "description", "location", "start_time", "end_time", "participants"]
        
        # Use LLM to generate missing fields intelligently
        prompt = f"""Generate complete meeting details for this scheduling request.

User Query: "{query}"
Time Slot: {time_slot.get('start_time')} to {time_slot.get('end_time')}

Mentioned Details: {json.dumps(mentioned, indent=2)}

Template Meeting (for reference):
{json.dumps(template_meeting, indent=2) if template_meeting else "No template available"}

Generate all required fields:
- meeting_id: Unique ID (format: meeting_<topic>_<timestamp>)
- title: Clear meeting title
- description: Brief description (infer from query if not explicit)
- location: Meeting location (infer: "TBD", "Online", "Room XXX", etc.)
- start_time: {time_slot.get('start_time')}
- end_time: {time_slot.get('end_time')}
- participants: Array with at least user (email: you@nyu.edu, name: You, is_organizer: true)

Respond with JSON:
{{
  "complete": true,
  "meeting_id": "...",
  "title": "...",
  "description": "...",
  "location": "...",
  "start_time": "...",
  "end_time": "...",
  "participants": [...]
}}"""
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            details = json.loads(completion.choices[0].message.content)
            details["complete"] = True
            return details
        except Exception as e:
            logger.error(f"Detail gathering failed: {e}")
            return {
                "complete": False,
                "missing_info": "Unable to generate meeting details. Please provide: title, location, participants.",
                "partial": mentioned
            }
    
    def _format_confirmation(self, details: Dict) -> str:
        """Phase 4: Format meeting details for user confirmation."""
        participants_str = ", ".join([p["name"] for p in details.get("participants", [])])
        
        return f"""📋 **Meeting Confirmation**

**Title:** {details.get('title')}
**Description:** {details.get('description')}
**When:** {self._format_time(details.get('start_time'))} - {self._format_time(details.get('end_time'))}
**Location:** {details.get('location')}
**Participants:** {participants_str}
**Meeting ID:** {details.get('meeting_id')}"""
    
    def _format_time(self, iso_time: str) -> str:
        """Format ISO time to readable string."""
        try:
            dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00')).astimezone()
            return dt.strftime("%b %d, %Y at %I:%M %p %Z").replace(" 0", " ")
        except:
            return iso_time
    
    def _format_trace(self) -> str:
        """Format execution log for debugging."""
        if not self.execution_log:
            return "No trace available"
        
        trace = ["SchedulerAgent Trace:"]
        for step in self.execution_log:
            phase = step.get("phase", "unknown")
            if phase == "analyze":
                trace.append(f"  🔍 Analyze: Scheduling={step['intent'].get('is_scheduling')}")
            elif phase == "check_conflicts":
                trace.append(f"  ⚠️  Check: {step['conflicts']} conflicts found")
            elif phase == "gather_details":
                trace.append(f"  📝 Gather: Complete={step.get('complete')}")
            elif phase == "commit":
                trace.append(f"  ✅ Commit: Success={step.get('success')}")
        
        return "\n".join(trace)

    def _is_past_time_slot(self, time_slot: Optional[Dict]) -> bool:
        """Return True if requested start time is before now (local tz)."""
        if not time_slot or not time_slot.get("start_time"):
            return False
        try:
            now = datetime.now().astimezone()
            req_start = datetime.fromisoformat(time_slot["start_time"].replace('Z', '+00:00')).astimezone()
            return req_start < now
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────
    # Replacement follow-up flow
    # ──────────────────────────────────────────────────────────────────────
    def has_pending_followup(self) -> bool:
        return bool(self.pending_replacement or self.pending_confirmation)

    def process_followup(self, query: str, user_context: Dict) -> Optional[Dict]:
        """Handle follow-up inputs like 'replace', selection, or cancellations.
        Returns a response dict if handled, otherwise None to let caller continue normal flow.
        """
        if not self.pending_replacement:
            return None

        q = (query or "").strip().lower()
        ctx = self.pending_replacement

        # User opts to choose another time
        if any(x in q for x in ["another time", "different time", "other time", "pick another"]):
            self.pending_replacement = None
            return {
                "action": "choose_another_time",
                "message": "👍 No worries. Please provide a different time slot to try again.",
                "trace": self._format_trace()
            }

        # Initial replace request
        if ctx.get("stage") == "offer" and "replace" in q:
            conflicts = ctx.get("conflicts", [])
            if not conflicts:
                self.pending_replacement = None
                return {
                    "action": "error",
                    "message": "❌ No conflicts available to replace.",
                    "trace": self._format_trace()
                }
            if len(conflicts) == 1:
                # Single conflict - proceed to prepare new details and ask confirmation
                return self._prepare_replacement_confirmation(conflicts[0])
            else:
                # Ask the user which to replace
                lines = []
                for idx, m in enumerate(conflicts, 1):
                    lines.append(
                        f"{idx}. {m.get('title')} (ID: {m.get('meeting_id')}) — "
                        f"{self._format_time(m.get('start_time'))} to {self._format_time(m.get('end_time'))}"
                    )
                self.pending_replacement["stage"] = "await_selection"
                return {
                    "action": "replacement_select",
                    "message": (
                        "Which meeting do you want to replace? Reply with the number or meeting_id.\n"
                        + "\n".join(lines)
                    ),
                    "trace": self._format_trace()
                }

        # Selection by index or meeting_id
        if ctx.get("stage") == "await_selection":
            conflicts = ctx.get("conflicts", [])
            selection = None
            # Try index
            if q.isdigit():
                i = int(q) - 1
                if 0 <= i < len(conflicts):
                    selection = conflicts[i]
            # Try meeting_id
            if not selection:
                selection = next((m for m in conflicts if m.get("meeting_id", "").lower() == q), None)
            if not selection:
                return {
                    "action": "replacement_select",
                    "message": "I couldn't match that. Please reply with a valid number or meeting_id.",
                    "trace": self._format_trace()
                }
            return self._prepare_replacement_confirmation(selection)

        # Unrecognized follow-up
        return {
            "action": "awaiting_followup",
            "message": "Please reply 'replace' to proceed, 'another time' to try a different slot, or select which meeting to replace.",
            "trace": self._format_trace()
        }

    def _prepare_replacement_confirmation(self, to_replace: Dict) -> Dict:
        """Gather details for the new meeting and set pending confirmation with replacement."""
        ctx = self.pending_replacement or {}
        # Build a pseudo-intent to reuse gather method
        pseudo_intent = {
            "time_slot": ctx.get("time_slot", {}),
            "mentioned_details": ctx.get("mentioned", {})
        }
        # Use the original query if available
        query = ctx.get("original_query", "Schedule a meeting")
        details = self._gather_meeting_details(query, pseudo_intent, {"user": {"email": ctx.get("user_email")}})
        if not details.get("complete"):
            return {
                "action": "need_info",
                "message": f"📝 To proceed with replacement, I need: {details.get('missing_info')}",
                "details": details,
                "trace": self._format_trace()
            }
        # Attach replacement metadata and request confirmation
        details["replace_meeting_id"] = to_replace.get("meeting_id")
        details["replace_title"] = to_replace.get("title")
        self.pending_confirmation = details
        # Clear replacement context; next user reply ('yes') will commit
        self.pending_replacement = None
        msg = self._format_confirmation(details)
        msg += f"\n\nThis will replace: {to_replace.get('title')} (ID: {to_replace.get('meeting_id')})."
        return {
            "action": "schedule_pending",
            "message": msg + "\n\n✅ Reply 'yes' or 'confirm' to replace and add the new meeting.",
            "details": details,
            "needs_confirmation": True,
            "trace": self._format_trace()
        }
