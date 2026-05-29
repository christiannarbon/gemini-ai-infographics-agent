from __future__ import annotations

from vertexai.agent_engines import AdkApp

from agent.adk_agent import build_runtime_workflow_agent


root_agent = AdkApp(agent=build_runtime_workflow_agent())
