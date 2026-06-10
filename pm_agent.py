import os
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from llm_tracker import LLMTracker

SKILL_FILE = "prompts/project_manager.txt"
DEFAULT_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"


def _read_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")
    return file_path.read_text(encoding="utf-8").strip()


def _build_prompt(task_description: str, skill_text: str) -> str:
    return (
        f"{skill_text.strip()}\n\n"
        f"User request:\n{task_description.strip()}\n\n"
        "Produce a simple architecture workflow that shows the major components, data flows, and integration points. "
        "Keep the output short, clear, and formatted as numbered steps or bullet points."
    )


class PmAgent:
    def __init__(self, model: str = DEFAULT_MODEL, skill_file: str = SKILL_FILE) -> None:
        load_dotenv()
        self.model = model
        self.skill_text = _read_file(skill_file)
        self.llm = LLMTracker(model=self.model)

    def run(self, task_description: str) -> str:
        prompt = _build_prompt(task_description, self.skill_text)

        return self.llm.generate(
            prompt=prompt,
            event_name="architecture-workflow",
            metadata={
                "skill_file": SKILL_FILE,
                "workflow_type": "architecture",
                "source": "pm_agent",
            },
            max_new_tokens=400,
            temperature=0.2,
        )

