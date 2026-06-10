import os
from dotenv import load_dotenv

from llm_tracker import LLMTracker

load_dotenv()

SYSTEM_PROMPT = """
You are a Project Manager Agent.

Generate:
1. Project Summary
2. Architecture
3. Tasks
4. Testing
5. Deployment
"""

llm = LLMTracker()


def project_manager_agent(project_idea: str) -> str:
    prompt = (
        f"{SYSTEM_PROMPT.strip()}\n\n"
        f"User: {project_idea.strip()}\n\n"
        "Please provide the requested output in a concise, structured format."
    )

    return llm.generate(
        prompt=prompt,
        event_name="project_manager_agent",
        metadata={"workflow": "project-management", "route": "main.py"},
        max_new_tokens=800,
        temperature=0.2,
    )
