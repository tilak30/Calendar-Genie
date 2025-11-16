import os
import json
import requests
from typing import List, Tuple, Optional
from pathlib import Path
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

class SmartFetcherAgent:
    """
    Agent that decides:
    1. Do we need THEORY from RAG?
    2. Do we need PRACTICE/EXAMPLES from web?
    3. Or MEETINGS data from meeting.json?
    
    Then fetches from appropriate sources
    """
    
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.model = "anthropic/claude-3-5-sonnet"
        self.meetings = self._load_meetings()
        self.rag_docs_dir = os.getenv("RAG_DOCS_DIR", "local_files")
        # LlamaIndex lazy init fields
        self._rag_index = None
        self._rag_ready = False
        self._rag_error: Optional[str] = None
    
    def _load_meetings(self) -> list:
        """Load all meetings from meeting.json"""
        try:
            with open('meeting.json', 'r') as f:
                data = json.load(f)
                return data.get('meetings', [])
        except Exception as e:
            print(f"Error loading meetings: {e}")
            return []
    
    def decide_what_to_fetch(self, query: str, meeting: dict) -> dict:
        """Agent decides: theory? practice? both?"""
        
        prompt = f"""Meeting: {meeting['title']}
Query: "{query}"

Agent decides what to fetch:
- "theory": Get underlying concepts/theory
- "practice": Get examples/exercises/how-to
- "both": Need both theory and practice

Respond JSON:
{{"fetch_type": "theory|practice|both"}}"""
        
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        import json
        response = json.loads(completion.choices[0].message.content)
        return response
    
    def fetch_all(self, query: str, meeting: dict) -> dict:
        """Fetch content based on agent's decision"""
        
        # Step 1: Agent decides what to fetch
        # fetch_plan = self.decide_what_to_fetch(query, meeting)
        # fetch_type = fetch_plan.get("fetch_type", "both")
        
        # Step 2: Fetch from appropriate sources
        content = {}

        # Reload meetings fresh on every fetch for up-to-date data
        self.meetings = self._load_meetings()

        # Check if query is asking about meetings or references meeting-related entities
        meetings_matches, meetings_text = self._fetch_from_meetings(query)
        if meetings_text:
            # Human-readable summary for LLM summarization
            content["meetings"] = meetings_text
        if meetings_matches:
            # Structured meeting objects for downstream usage
            content["meetings_structured"] = meetings_matches

        # Local RAG per main.py logic (llama_index when available)
        rag_content = self._fetch_from_rag(query)
        content["rag"] = rag_content

        # Web search disabled per requirement (no Tavily/externals)
        content["web"] = ""

        return content
    
    def _fetch_from_meetings(self, query: str):
        """Search meeting.json for relevant meetings.

        Returns (matches_list, human_readable_text).
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
                limit = self._extract_number(query_lower) or 3
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
    
    def _fetch_from_rag(self, query: str) -> str:
        """Local RAG using llama_index if available; fallback to simple token scoring.

        - Primary: Build/load a vector index over `self.rag_docs_dir` and retrieve top chunks.
        - Fallback: Simple token-based paragraph scoring over files in `self.rag_docs_dir`.
        Returns raw concatenated text snippets; higher-level code will summarize.
        """
        # Try vector retrieval via llama_index
        try:
            rag_text = self._rag_retrieve_with_llama_index(query)
            if rag_text is not None:
                return rag_text
        except Exception as e:
            logger.warning(f"LlamaIndex retrieval failed, falling back. Error: {e}")

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

    def _rag_retrieve_with_llama_index(self, query: str) -> Optional[str]:
        """Attempt retrieval using llama_index. Returns text or None if unavailable."""
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
            return None

        index_dir = os.getenv("RAG_INDEX_DIR", "index_storage")
        docs_dir = self.rag_docs_dir

        try:
            # Initialize index if not ready
            if not self._rag_ready:
                # Try loading from disk
                try:
                    storage_context = StorageContext.from_defaults(persist_dir=index_dir)
                    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
                    self._rag_index = load_index_from_storage(storage_context)
                    self._rag_ready = True
                except Exception:
                    # Build new index from documents
                    if not os.path.exists(docs_dir):
                        os.makedirs(docs_dir, exist_ok=True)
                    documents = SimpleDirectoryReader(docs_dir).load_data()
                    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
                    Settings.node_parser = SentenceSplitter(chunk_size=256, chunk_overlap=20)
                    self._rag_index = VectorStoreIndex.from_documents(documents)
                    self._rag_index.storage_context.persist(persist_dir=index_dir)
                    self._rag_ready = True

            if not self._rag_index:
                return None

            # Retrieve top chunks
            retriever = self._rag_index.as_retriever(similarity_top_k=3)
            retrieved_nodes = retriever.retrieve(query)
            if not retrieved_nodes:
                return ""

            # Optional threshold similar to main.py
            try:
                top_score = retrieved_nodes[0].score
                if top_score is not None and top_score < 0.7:
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
