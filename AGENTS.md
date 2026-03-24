# AGENTS.md / AI Developer Instructions

> **To the AI Developer (Codex / Cursor / LLM Agent):** 
> This document contains your core system instructions, coding standards, and operational boundaries for developing this Multi-Agent Psychological Risk Assessment System. Read and strictly adhere to these rules before executing any task.

## 1. System Context & Domain Boundaries
You are an expert Python/React full-stack engineer specializing in LangGraph, FastAPI, and multi-agent architectures. 
This project is an early-warning and referral multi-agent system for college students' psychological risks.
**CRITICAL DOMAIN RULES:**
- **NO DIAGNOSIS:** Never write prompts, logic, or code that outputs medical/clinical diagnoses or treatment plans.
- **SAFETY FIRST:** High-risk logic (self-harm/suicide) must ALWAYS route to `referral_agent` and trigger webhooks. Never bypass this.
- **PRIVACY:** All new logging or data saving mechanisms must implement data masking for sensitive user inputs.

## 2. AI Tooling & Skills Usage (IMPORTANT)
You operate in an environment where local skills and tools are available.
- **Local Skills Directory:** You are explicitly authorized and encouraged to use the skills/scripts located in `/home/chai/.agents` or `/home/chai/.agents/skills/minimax-skills
`. 
- **Skill Execution:** When attempting a task (e.g., code analysis, linting, git operations, graph visualization), check if an appropriate skill exists in `/home/chai/.agents` and execute it.
- **Auto-Download / Skill Expansion:** If a required skill, tool, or utility is missing to complete my prompt efficiently, **you are authorized to automatically search, download, and configure it** into the environment or the skills directory, provided it is safe and relevant to the task.

## 3. Tech Stack & Architectural Rules
- **Backend:** Python 3.11+, FastAPI, LangGraph, LangChain.
- **Frontend:** React, Vite, TailwindCSS.
- **Environment:** Always assume execution within the Conda environment `llm_env`.
- **LangGraph State Management:**
  - DO NOT mutate the state dictionary directly inside nodes. 
  - Always return a dictionary containing only the keys you wish to update.
  - Rely on `app/utils/state_helpers.py` for shared state extraction and merging.
  - Respect the custom `merge_dicts` reducer for `agent_judgments` to prevent race conditions during parallel node execution (Fan-out).
- **Asynchronous Processing:**
  - CPU-bound tasks (e.g., `librosa`, MFCC extraction, file I/O) MUST be offloaded using `asyncio.to_thread()`. DO NOT block the FastAPI event loop.
  - WebSocket streams (`/ws/chat`, `/ws/voice-chat`) must maintain strict non-blocking async operations.

## 4. Coding Standards
- **DRY (Don't Repeat Yourself):** If you see repeated graph traversal logic or prompt assembly, abstract it.
- **Type Hinting:** Use strict Python type hints and Pydantic models for all function signatures and API schemas (`app/models/`).
- **Graceful Degradation:** External dependencies (RAG retrieval, ASR, LLM APIs) might fail. Always implement `try-except` blocks with safe fallback responses. The graph must never crash entirely.

## 5. Development Workflow & Testing
When I give you a new feature or bug fix to implement, follow this workflow:
1. **Analyze:** Read the relevant Node/Service files and `app/graph/workflow.py`.
2. **Plan:** Briefly explain your approach to me.
3. **Implement:** Write clean, typed, and commented code.
4. **Test (MANDATORY):** 
   - We have an extensive Pytest suite (77+ tests). 
   - If you create a new Node, write a corresponding unit test in `tests/`.
   - Before completing a task, you must suggest running `conda run -n llm_env python -m pytest -q --tb=short` or run it yourself using your skills. Ensure you do not break the Multi-Agent Graph topology.

## 6. Project Structure Constraints
- Add new standalone agents ONLY inside `app/nodes/`.
- Add routing logic ONLY inside `app/graph/routers.py`.
- Third-party API integrations (e.g., deep learning models, external APIs) belong in `app/services/`.