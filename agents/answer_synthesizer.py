import os
from openai import OpenAI

class AnswerSynthesizer:
    """Uses Claude to write coherent answer from multiple sources"""
    
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.model = "anthropic/claude-3-5-sonnet"
    
    def synthesize(self, 
                   query: str,
                   sources: dict,
                   meeting_data: dict) -> str:
        """
        sources = {
            "drive": "Content from Person 3's RAG...",
            "web": "Content from web search...",
            "history": "From previous discussion..."
        }
        """
        
        # Build source text
        source_text = ""
        
        if sources.get("drive"):
            source_text += f"INTERNAL (From course materials):\n{sources['drive']}\n\n"
        
        if sources.get("web"):
            source_text += f"EXTERNAL (From web research):\n{sources['web']}\n\n"
        
        if sources.get("history"):
            source_text += f"FROM EARLIER:\n{sources['history']}\n\n"
        
        # Prompt Claude to synthesize
        prompt = f"""Meeting: {meeting_data['title']}

Student Question: "{query}"

Available Information:
{source_text}

---

Write a clear, helpful answer for the student based on the above information.
- Be concise (2-3 paragraphs)
- Connect internal + external info if both are available
- Reference sources naturally
- Answer what the student actually needs"""
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            answer = completion.choices[0].message.content
            return answer
            
        except Exception as e:
            return f"Error generating answer: {str(e)}"
