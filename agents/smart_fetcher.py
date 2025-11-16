import os
import json
import requests
from typing import List, Tuple, Optional
from pathlib import Path
from openai import OpenAI
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Ensure env vars from .env are loaded when running outside server
load_dotenv()

class SmartFetcherAgent:
    """
    ReAct-style Agent for intelligent content retrieval.
    
    Capabilities:
    1. Planning: Analyzes query and decides retrieval strategy
    2. Tool Selection: Chooses between meetings, RAG, and web sources
    3. Execution: Fetches content with adaptive parameters
    4. Reflection: Evaluates quality and decides if refinement needed
    5. Memory: Tracks past queries and successful strategies
    
    Tools Available:
    - meetings_search: Schedule-aware meeting retrieval
    - rag_search: Vector/keyword document search
    - web_search: External research (currently disabled)
    """
    
    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        ) if api_key else None
        self.model = "anthropic/claude-3-5-sonnet"
        self.meetings = self._load_meetings()
        # Point to meetings_bundle where your RAG docs live
        self.rag_docs_dir = os.getenv("RAG_DOCS_DIR", "meetings_bundle")
        # LlamaIndex lazy init fields
        self._rag_index = None
        self._rag_ready = False
        self._rag_error: Optional[str] = None
        
        # Agent state and memory
        self.query_history: List[dict] = []  # Past queries and strategies
        self.current_plan: Optional[dict] = None
        self.execution_trace: List[dict] = []  # Step-by-step execution log
    
    def _load_meetings(self) -> list:
        """Load all meetings from meeting.json"""
        try:
            with open('meeting.json', 'r') as f:
                data = json.load(f)
                return data.get('meetings', [])
        except Exception as e:
            print(f"Error loading meetings: {e}")
            return []
    
    def _plan_retrieval(self, query: str, meeting: dict) -> dict:
        """Phase 1: Plan retrieval strategy using LLM reasoning.
        
        The agent analyzes the query and decides:
        - Which tools to use (meetings, rag, web)
        - Priority/order of execution
        - Parameters (limits, thresholds)
        - Reasoning for the strategy
        """
        
        # Build context from query history for better planning
        history_context = ""
        if self.query_history:
            recent = self.query_history[-3:]  # Last 3 queries
            history_context = "\\n".join([
                f"- Query: '{h['query'][:50]}' → Strategy: {h['plan'].get('strategy')}"
                for h in recent
            ])
        
        prompt = f"""You are a retrieval planning agent. Analyze the query and create an optimal retrieval strategy.

Current Meeting Context:
- Title: {meeting.get('title', 'Unknown')}
- Description: {meeting.get('description', '')}
- Time: {meeting.get('start_time', 'N/A')}

User Query: "{query}"

Recent Query History:
{history_context if history_context else "(No history)"}

Available Tools:
1. meetings: Search meeting.json for schedule/participants/locations
   - Best for: "when", "who", "where", today/tomorrow/next queries
   - Parameters: meeting_limit (1-10)

2. rag: Search local documents (meetings_bundle) via vector/keyword
   - Best for: "what", "why", "how", explanation queries, technical details
   - Parameters: rag_chunks (1-5), rag_threshold (0.5-0.9)

3. web: External search (currently disabled)

Create a retrieval plan with:
- strategy: "schedule"|"context"|"hybrid"
- tools: List of tools to use in order ["meetings", "rag", "web"]
- priority: Which tool is most important
- reasoning: Why this strategy?
- parameters: {{meeting_limit: int, rag_chunks: int, rag_threshold: float}}

Respond with JSON only:
{{
  "strategy": "...",
  "tools": ["...", "..."],
  "priority": "...",
  "reasoning": "...",
  "parameters": {{...}}
}}"""
        
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3  # Lower temp for more consistent planning
        )
        
        try:
            plan = json.loads(completion.choices[0].message.content)
            self.execution_trace.append({"phase": "planning", "plan": plan})
            return plan
        except Exception as e:
            logger.warning(f"Planning failed: {e}, using default strategy")
            # Fallback to heuristic planning
            return self._heuristic_plan(query)
    
    def _heuristic_plan(self, query: str) -> dict:
        """Fallback: Rule-based planning when LLM planning fails."""
        ql = query.lower()
        
        # Schedule queries
        if any(kw in ql for kw in ["today", "tomorrow", "next", "upcoming", "schedule", "when"]):
            return {
                "strategy": "schedule",
                "tools": ["meetings"],
                "priority": "meetings",
                "reasoning": "Schedule-related query detected",
                "parameters": {"meeting_limit": 5, "rag_chunks": 0}
            }
        
        # Context/explanation queries
        if any(kw in ql for kw in ["explain", "why", "how", "what is", "tell me about", "details"]):
            return {
                "strategy": "context",
                "tools": ["rag", "meetings"],
                "priority": "rag",
                "reasoning": "Explanation query, prioritize documents",
                "parameters": {"meeting_limit": 2, "rag_chunks": 5, "rag_threshold": 0.6}
            }
        
        # Default: balanced approach
        return {
            "strategy": "hybrid",
            "tools": ["meetings", "rag"],
            "priority": "balanced",
            "reasoning": "General query, use all sources",
            "parameters": {"meeting_limit": 3, "rag_chunks": 3, "rag_threshold": 0.7}
        }
    
    def _execute_plan(self, query: str, plan: dict) -> dict:
        """Phase 2: Execute the retrieval plan using selected tools."""
        content = {}
        tools = plan.get("tools", ["meetings", "rag"])
        params = plan.get("parameters", {})
        
        logger.info(f"Executing with tools: {tools}")
        
        # Execute meetings search if selected
        if "meetings" in tools:
            try:
                meetings_matches, meetings_text = self._fetch_from_meetings(
                    query, 
                    limit=params.get("meeting_limit", 3)
                )
                if meetings_text:
                    content["meetings"] = meetings_text
                if meetings_matches:
                    content["meetings_structured"] = meetings_matches
                self.execution_trace.append({
                    "phase": "execution",
                    "tool": "meetings",
                    "found": len(meetings_matches)
                })
            except Exception as e:
                logger.error(f"Meetings search failed: {e}")
        
        # Execute RAG search if selected
        if "rag" in tools:
            try:
                rag_content = self._fetch_from_rag(
                    query,
                    top_k=params.get("rag_chunks", 3),
                    threshold=params.get("rag_threshold", 0.7)
                )
                content["rag"] = rag_content
                self.execution_trace.append({
                    "phase": "execution",
                    "tool": "rag",
                    "found": len(rag_content) > 0
                })
            except Exception as e:
                logger.error(f"RAG search failed: {e}")
        
        # Web search disabled
        content["web"] = ""
        
        return content
    
    def _reflect_and_refine(self, query: str, content: dict, plan: dict) -> dict:
        """Phase 3: Evaluate retrieval quality and refine if needed.
        
        Reflection criteria:
        - Did we get any results?
        - Are results relevant to the query?
        - Should we retry with different parameters?
        """
        has_meetings = bool(content.get("meetings"))
        has_rag = bool(content.get("rag"))
        
        # Quality check
        if not has_meetings and not has_rag:
            logger.warning("No results found, attempting refinement")
            # Try more lenient search
            if "rag" in plan.get("tools", []):
                refined_rag = self._fetch_from_rag(query, top_k=5, threshold=0.5)
                if refined_rag:
                    content["rag"] = refined_rag
                    logger.info("Refinement successful with lower threshold")
                    content["refined"] = True
        
        # Add success flag
        content["success"] = has_meetings or has_rag
        
        self.execution_trace.append({
            "phase": "reflection",
            "quality": "good" if content["success"] else "poor",
            "refined": content.get("refined", False)
        })
        
        return content
    
    def get_execution_summary(self) -> str:
        """Get human-readable summary of last execution for debugging."""
        if not self.execution_trace:
            return "No execution trace available"
        
        summary = ["Agent Execution Trace:"]
        for step in self.execution_trace:
            phase = step.get("phase", "unknown")
            if phase == "planning":
                summary.append(f"  📋 Plan: {step['plan'].get('strategy')} - {step['plan'].get('reasoning')}")
            elif phase == "execution":
                tool = step.get("tool")
                found = step.get("found")
                summary.append(f"  🔧 Tool: {tool} - Found: {found}")
            elif phase == "reflection":
                quality = step.get("quality")
                refined = step.get("refined", False)
                summary.append(f"  🤔 Quality: {quality}" + (" (refined)" if refined else ""))
        
        return "\n".join(summary)
    
    def decide_what_to_fetch(self, query: str, meeting: dict) -> dict:
        """Legacy method - now delegates to _plan_retrieval"""
        plan = self._plan_retrieval(query, meeting)
        return {"fetch_type": plan.get("strategy", "both")}
        
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        import json
        response = json.loads(completion.choices[0].message.content)
        return response
    
    def fetch_all(self, query: str, meeting: dict) -> dict:
        """Main agent loop: Plan → Execute → Reflect"""
        logger.info(f"Agent starting retrieval for query: {query[:100]}")
        self.execution_trace = []
        
        # Reload meetings fresh
        self.meetings = self._load_meetings()
        
        # PHASE 1: Planning
        plan = self._plan_retrieval(query, meeting)
        self.current_plan = plan
        logger.info(f"Agent plan: {plan.get('strategy', 'unknown')}")
        
        # PHASE 2: Execute plan with selected tools
        content = self._execute_plan(query, plan)
        
        # PHASE 3: Reflect on quality and refine if needed
        refined = self._reflect_and_refine(query, content, plan)
        
        # Store in history for learning
        self.query_history.append({
            "query": query,
            "plan": plan,
            "trace": self.execution_trace,
            "success": refined.get("success", True)
        })
        
        return refined
    
    def _fetch_from_meetings(self, query: str, limit: int = 3):
        """Search meeting.json for relevant meetings.

        Returns (matches_list, human_readable_text).
        Args:
            query: User query string
            limit: Maximum number of meetings to return for upcoming/next queries
        """
        if not self.meetings:
            return [], ""

        query_lower = (query or '').lower()

        # If the user is asking explicitly about schedule (today/tomorrow/next/upcoming),
        # handle this first and return chronologically appropriate meetings.
        if any(kw in query_lower for kw in ["today", "tomorrow", "next", "upcoming", "schedule", "agenda"]):
            # Decide which set to return
            if "today" in query_lower:
                items = self._meetings_on_day(offset_days=0)
                if not items:
                    return [], self._no_meetings_message(label="today")
            elif "tomorrow" in query_lower:
                items = self._meetings_on_day(offset_days=1)
                if not items:
                    return [], self._no_meetings_message(label="tomorrow")
            else:
                limit = self._extract_number(query_lower) or limit  # Use agent's planned limit
                items = self._get_upcoming_meetings(limit=limit)
                if not items:
                    return [], "No upcoming meetings found."

            # Annotate status and craft tense-aware text
            annotated = []
            text = "NEXT MEETINGS:\n" if ("next" in query_lower or "upcoming" in query_lower) else "MATCHING MEETINGS:\n"
            for m in items:
                status = self._meeting_status_flag(m)
                mm = dict(m)
                mm["_status"] = status
                annotated.append(mm)
                when_str = self._format_meeting_when(m.get('start_time'))
                if status == "past":
                    line = (
                        f"\n- {m.get('title')}\n"
                        f"  Took place: {when_str}\n"
                        f"  Location: {m.get('location')}\n"
                        f"  Focus: {m.get('description')}\n"
                    )
                elif status == "ongoing":
                    line = (
                        f"\n- {m.get('title')}\n"
                        f"  Happening now: {when_str}\n"
                        f"  Location: {m.get('location')}\n"
                        f"  Focus: {m.get('description')}\n"
                    )
                else:
                    line = (
                        f"\n- {m.get('title')}\n"
                        f"  Scheduled: {when_str}\n"
                        f"  Location: {m.get('location')}\n"
                        f"  Focus: {m.get('description')}\n"
                    )
                text += line
            return annotated, text

        # If user explicitly asked to list all meetings, return full list
        if 'all meetings' in query_lower or query_lower.strip() in ['list meetings', 'show meetings', 'list all meetings', 'show all meetings']:
            text_parts = []
            for m in self.meetings:
                text_parts.append(json.dumps(m))
            return self.meetings, '\n\n'.join(text_parts)

        # Token-based matching across title/description/location/participants
        tokens = [t for t in query_lower.split() if len(t) > 2]
        matches = []
        for m in self.meetings:
            hay = ' '.join([
                str(m.get('title','')),
                str(m.get('description','')),
                str(m.get('location','')),
                ' '.join([p.get('name','') + ' ' + p.get('email','') for p in m.get('participants', [])])
            ]).lower()
            if any(tok in hay for tok in tokens):
                matches.append(m)

        if matches:
            meetings_text = "MATCHING MEETINGS:\n"
            annotated = []
            for meeting in matches:
                status = self._meeting_status_flag(meeting)
                mm = dict(meeting)
                mm["_status"] = status
                annotated.append(mm)
                when_str = self._format_meeting_when(meeting.get('start_time'))
                if status == "past":
                    meetings_text += (
                        f"\n- Title: {meeting.get('title')}\n"
                        f"  Took place: {when_str}\n"
                        f"  Location: {meeting.get('location')}\n"
                        f"  Description: {meeting.get('description')}\n"
                        f"  Participants: {', '.join([p.get('name','') for p in meeting.get('participants', [])])}\n"
                    )
                elif status == "ongoing":
                    meetings_text += (
                        f"\n- Title: {meeting.get('title')}\n"
                        f"  Happening now: {when_str}\n"
                        f"  Location: {meeting.get('location')}\n"
                        f"  Description: {meeting.get('description')}\n"
                        f"  Participants: {', '.join([p.get('name','') for p in meeting.get('participants', [])])}\n"
                    )
                else:
                    meetings_text += (
                        f"\n- Title: {meeting.get('title')}\n"
                        f"  Scheduled: {when_str}\n"
                        f"  Location: {meeting.get('location')}\n"
                        f"  Description: {meeting.get('description')}\n"
                        f"  Participants: {', '.join([p.get('name','') for p in meeting.get('participants', [])])}\n"
                    )
            return annotated, meetings_text

        # If user explicitly asks for upcoming/next/today/tomorrow schedule
        if any(kw in query_lower for kw in ["upcoming", "next", "today", "tomorrow", "schedule", "agenda"]):
            # Already handled above; fallthrough here only if something slipped through
            upcoming = self._get_upcoming_meetings(limit=self._extract_number(query_lower) or 3)
            if upcoming:
                text = "NEXT MEETINGS:\n"
                for m in upcoming:
                    when_str = self._format_meeting_when(m.get('start_time'))
                    text += (
                        f"\n- {m.get('title')}\n"
                        f"  When: {when_str}\n"
                        f"  Location: {m.get('location')}\n"
                        f"  Description: {m.get('description')}\n"
                    )
                return upcoming, text

        return [], ""

    def _meeting_status_flag(self, meeting: dict) -> str:
        """Return 'past', 'ongoing', or 'upcoming' based on current local time."""
        try:
            from datetime import datetime
            start = meeting.get('start_time')
            end = meeting.get('end_time')
            if not start:
                return "upcoming"
            start_dt = datetime.fromisoformat(str(start).replace('Z', '+00:00')).astimezone()
            now = datetime.now().astimezone()
            if end:
                end_dt = datetime.fromisoformat(str(end).replace('Z', '+00:00')).astimezone()
            else:
                end_dt = start_dt
            if end_dt < now:
                return "past"
            if start_dt <= now <= end_dt:
                return "ongoing"
            return "upcoming"
        except Exception:
            return "upcoming"

    def _extract_number(self, text: str) -> int:
        try:
            import re
            nums = re.findall(r"(\d+)", text)
            if nums:
                n = int(nums[0])
                if 1 <= n <= 10:
                    return n
        except Exception:
            pass
        return 0

    def _get_upcoming_meetings(self, limit: int = 3) -> List[dict]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        items: List[Tuple[dict, datetime]] = []
        for m in self.meetings:
            try:
                dt = datetime.fromisoformat(m.get('start_time', '').replace('Z', '+00:00'))
                if dt >= now:
                    items.append((m, dt))
            except Exception:
                continue
        items.sort(key=lambda x: x[1])
        return [m for m, _ in items[:limit]]

    def _meetings_on_day(self, offset_days: int) -> List[dict]:
        from datetime import datetime, timedelta
        results: List[dict] = []
        now_local = datetime.now().astimezone()
        target_date = (now_local + timedelta(days=offset_days)).date()
        for m in self.meetings:
            try:
                dt_local = datetime.fromisoformat(m.get('start_time', '').replace('Z', '+00:00')).astimezone()
                if dt_local.date() == target_date:
                    results.append(m)
            except Exception:
                continue
        # Sort by local time
        results.sort(key=lambda mm: datetime.fromisoformat(mm.get('start_time', '').replace('Z', '+00:00')).astimezone())
        return results

    def _no_meetings_message(self, label: str) -> str:
        from datetime import datetime, timedelta
        now_local = datetime.now().astimezone()
        if label == "today":
            day_label = now_local.strftime("%b %d, %Y")
        elif label == "tomorrow":
            day_label = (now_local + timedelta(days=1)).strftime("%b %d, %Y")
        else:
            day_label = label
        return f"No meetings scheduled for {label} ({day_label})."

    def _format_meeting_when(self, start_time_str: str) -> str:
        """Return a relative label like 'today', 'tomorrow', weekday, with local time and date."""
        try:
            from datetime import datetime, timezone
            if not start_time_str:
                return "Unknown time"
            dt_utc = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            local_dt = dt_utc.astimezone()  # convert to local timezone
            now_local = datetime.now().astimezone()
            day_diff = (local_dt.date() - now_local.date()).days

            if day_diff == 0:
                day_label = "today"
            elif day_diff == 1:
                day_label = "tomorrow"
            elif 2 <= day_diff <= 6:
                day_label = local_dt.strftime("%A")
            else:
                day_label = local_dt.strftime("%b %d")

            # Time like 2:00 PM, without leading zero on hour
            time_str = local_dt.strftime("%I:%M %p").lstrip('0')
            date_str = local_dt.strftime("%b %d, %Y")
            return f"{day_label} ({date_str}) at {time_str}"
        except Exception:
            return start_time_str or "Unknown time"
    
    def _fetch_from_rag(self, query: str, top_k: int = 3, threshold: float = 0.7) -> str:
        """Local RAG using llama_index if available; fallback to simple token scoring.

        - Primary: Build/load a vector index over `self.rag_docs_dir` and retrieve top chunks.
        - Fallback: Simple token-based paragraph scoring over files in `self.rag_docs_dir`.
        Returns raw concatenated text snippets; higher-level code will summarize.
        
        Args:
            query: User query string
            top_k: Number of chunks to retrieve (vector search)
            threshold: Minimum similarity score for vector results
        """
        # Try vector retrieval via llama_index
        try:
            logger.info(f"Attempting vector RAG retrieval for query: {query[:80]}")
            rag_text = self._rag_retrieve_with_llama_index(query, top_k=top_k, threshold=threshold)
            if rag_text is not None:
                logger.info("Vector RAG retrieval succeeded")
                return rag_text
            else:
                logger.warning("Vector RAG returned None, using fallback")
        except Exception as e:
            logger.warning(f"LlamaIndex retrieval failed, falling back. Error: {e}")
            import traceback
            logger.debug(traceback.format_exc())

        # Fallback: simple local paragraph scoring
        try:
            docs = self._gather_local_documents()
            if not docs:
                return ""

            q_tokens = [t for t in (query or "").lower().split() if len(t) > 2]
            candidates: List[Tuple[int, str, str]] = []  # (score, file, snippet)

            for file_path, content in docs:
                parts = [p.strip() for p in content.split("\n\n") if p.strip()]
                for para in parts:
                    lower = para.lower()
                    score = sum(1 for t in q_tokens if t in lower)
                    if score > 0:
                        candidates.append((score, str(file_path), para))

            if not candidates:
                return ""

            candidates.sort(key=lambda x: x[0], reverse=True)
            top = candidates[:5]

            snippets = []
            for score, fpath, para in top:
                snippets.append(f"[Source: {Path(fpath).name} | score={score}]\n{para}")

            return "\n\n".join(snippets)

        except Exception as e:
            logger.error(f"RAG local search error: {e}")
            return ""

    def _rag_retrieve_with_llama_index(self, query: str, top_k: int = 3, threshold: float = 0.7) -> Optional[str]:
        """Attempt retrieval using llama_index. Returns text or None if unavailable.
        
        Args:
            query: User query string
            top_k: Number of similar chunks to retrieve
            threshold: Minimum similarity score to include a result
        """
        try:
            # Lazy import to avoid hard dependency at import time
            from llama_index.core import (
                SimpleDirectoryReader,
                VectorStoreIndex,
                StorageContext,
                load_index_from_storage,
            )
            from llama_index.core.settings import Settings
            from llama_index.core.node_parser import SentenceSplitter
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        except Exception as e:
            self._rag_error = f"llama_index not available: {e}"
            logger.warning(f"Could not import llama_index: {e}")
            return None

        index_dir = os.getenv("RAG_INDEX_DIR", "index_storage")
        docs_dir = self.rag_docs_dir

        try:
            # Initialize index if not ready
            if not self._rag_ready:
                # Try loading from disk
                try:
                    logger.info(f"Attempting to load vector index from {index_dir}")
                    storage_context = StorageContext.from_defaults(persist_dir=index_dir)
                    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
                    self._rag_index = load_index_from_storage(storage_context)
                    self._rag_ready = True
                    logger.info("Vector index loaded from disk")
                except Exception as load_err:
                    # Build new index from documents
                    logger.info(f"Index load failed ({load_err}), building new index from {docs_dir}")
                    if not os.path.exists(docs_dir):
                        logger.warning(f"Docs directory {docs_dir} does not exist, creating it")
                        os.makedirs(docs_dir, exist_ok=True)
                    documents = SimpleDirectoryReader(docs_dir).load_data()
                    if not documents:
                        logger.warning(f"No documents found in {docs_dir}")
                        self._rag_error = "No documents to index"
                        return None
                    logger.info(f"Building vector index from {len(documents)} documents")
                    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
                    Settings.node_parser = SentenceSplitter(chunk_size=256, chunk_overlap=20)
                    self._rag_index = VectorStoreIndex.from_documents(documents)
                    self._rag_index.storage_context.persist(persist_dir=index_dir)
                    self._rag_ready = True
                    logger.info(f"Vector index built and persisted to {index_dir}")

            if not self._rag_index:
                return None

            # Retrieve top chunks with agent-specified top_k
            retriever = self._rag_index.as_retriever(similarity_top_k=top_k)
            retrieved_nodes = retriever.retrieve(query)
            if not retrieved_nodes:
                return ""

            # Optional threshold filtering with agent-specified threshold
            try:
                top_score = retrieved_nodes[0].score
                if top_score is not None and top_score < threshold:
                    logger.info(f"Top score {top_score:.2f} below threshold {threshold}, returning empty")
                    return ""
            except Exception:
                pass

            context_for_llm = "\n\n---\n\n".join([node.get_content() for node in retrieved_nodes])
            source_files = sorted(list({node.metadata.get('file_name', 'Unknown') for node in retrieved_nodes}))
            header = f"[Vector RAG sources: {', '.join(source_files)}]"
            return f"{header}\n{context_for_llm}"

        except Exception as e:
            self._rag_error = f"RAG index error: {e}"
            return None

    def _gather_local_documents(self) -> List[Tuple[Path, str]]:
        """Load text documents from the configured RAG directory.

        Returns a list of (path, content) for .txt/.md/.html files.
        """
        results: List[Tuple[Path, str]] = []
        try:
            base = Path(self.rag_docs_dir)
            if not base.exists():
                return results
            exts = {".txt", ".md", ".html", ".htm"}
            for p in base.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    try:
                        text = p.read_text(encoding="utf-8", errors="ignore")
                        if text.strip():
                            results.append((p, text))
                    except Exception:
                        continue
        except Exception:
            return results
        return results
    
    def _fetch_from_web(self, query: str) -> str:
        """Web search disabled: return empty string."""
        return ""
