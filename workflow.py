"""Portable WorkflowService implementation with the native version-1 format.

 Copyright (c) 2026 Skylight Software Organization.
 Created by EternityBoundary
 All rights reserved.
 SPDX-License-Identifier: GPL-3.0-only
 
 File: workflow.py
 Project: AetherNexus for AstrBot
"""

import base64
import json
import math


def validate_workflow(flow: dict) -> dict:
    """Validate the native graph format before preview or code export.

    Args:
        flow: Version-1 workflow document.

    Returns:
        The validated document.

    Raises:
        ValueError: Graph structure or limits are invalid.
    """
    if not isinstance(flow, dict) or flow.get("version") != 1:
        raise ValueError("Expected workflow version 1.")
    nodes = flow.get("nodes")
    if (
        not isinstance(nodes, list)
        or not 1 <= len(nodes) <= 100
        or len(json.dumps(flow)) > 2 * 1024 * 1024
    ):
        raise ValueError("Workflow must contain 1–100 nodes and fit within 2 MiB.")
    ids = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("Invalid workflow node.")
        node_id = node.get("id")
        if (
            not isinstance(node_id, str)
            or not 1 <= len(node_id) <= 128
            or node_id in ids
        ):
            raise ValueError("Workflow node IDs must be unique non-empty strings.")
        ids.add(node_id)
        if node.get("kind") not in ("start", "agent", "condition", "transform", "end"):
            raise ValueError("Unsupported node kind.")
        for name in ("name", "instructions", "model", "next", "otherwise", "match"):
            if not isinstance(node.get(name, ""), str) or len(node.get(name, "")) > (
                1048576 if name in ("instructions", "match") else 256
            ):
                raise ValueError(f"Invalid node {name}.")
        for axis in ("x", "y"):
            pos = node.get(axis, 0)
            if (
                type(pos) not in (int, float)
                or not math.isfinite(pos)
                or not 0 <= pos <= 10000
            ):
                raise ValueError("Node coordinates must be between 0 and 10000.")
        if node["kind"] == "agent" and not node.get("model"):
            raise ValueError("Agent nodes require a model.")
    if (
        flow.get("entry") not in ids
        or next(n for n in nodes if n["id"] == flow["entry"])["kind"] != "start"
    ):
        raise ValueError("Entry must refer to a start node.")
    for node in nodes:
        if node["kind"] != "end" and node.get("next") not in ids:
            raise ValueError("Missing next node.")
        if node["kind"] == "condition" and node.get("otherwise") not in ids:
            raise ValueError("Missing alternate branch.")
    return flow


async def run_workflow(flow: dict, text: str, client, project: str = "") -> dict:
    """Run at most 64 graph steps with no arbitrary code execution.

    Args:
        flow: Native version-1 graph.
        text: Initial user input.
        client: Injected API client implementing request.
        project: Optional generation project header.

    Returns:
        Final output and ordered execution trace.

    Raises:
        ValueError: Validation fails or execution exceeds a limit.
    """
    validate_workflow(flow)
    if not isinstance(text, str) or len(text) > 1048576:
        raise ValueError("Workflow input exceeds 1 MiB.")
    nodes = {n["id"]: n for n in flow["nodes"]}
    current, trace = flow["entry"], []
    for _ in range(64):
        node = nodes[current]
        if node["kind"] == "end":
            return {"text": text, "steps": trace}
        event = {"node": node["id"], "kind": node["kind"]}
        if node["kind"] == "agent":
            answer = await client.request(
                "POST",
                "/responses",
                body={
                    "model": node["model"],
                    "instructions": node.get("instructions", ""),
                    "input": text,
                    "store": False,
                },
                project=project,
            )
            if answer.get("status") != "completed":
                raise ValueError("Agent response did not complete.")
            text = "".join(
                c.get("text", "")
                for out in answer.get("output", [])
                for c in out.get("content", [])
                if c.get("type") == "output_text"
            )
            event["response_id"] = answer.get("id")
        elif node["kind"] == "transform":
            template = node.get("instructions", "")
            if len(template) + template.count("{{input}}") * (len(text) - 9) > 1048576:
                raise ValueError("Transform exceeds 1 MiB.")
            text = template.replace("{{input}}", text)
        if len(text) > 1048576:
            raise ValueError("Workflow output exceeds 1 MiB.")
        current = (
            node["otherwise"]
            if node["kind"] == "condition" and node.get("match", "") not in text
            else node["next"]
        )
        trace.append({**event, "output": text, "next": current})
    raise ValueError("Workflow exceeded 64 steps.")


def export_python(flow: dict) -> str:
    """Export a standalone Agents SDK runner with graph content encoded as data.

    Args:
        flow: Native version-1 graph.

    Returns:
        Python source without credentials.
    """
    validate_workflow(flow)
    encoded = base64.b64encode(json.dumps(flow, ensure_ascii=False).encode()).decode()
    return (
        '''# Install: pip install openai-agents
# Set OPENAI_API_KEY in your environment.
import asyncio
import base64
import json
from agents import Agent, Runner, ModelSettings

workflow = json.loads(base64.b64decode("'''
        + encoded
        + """"))

async def run(text):
    nodes = {n["id"]: n for n in workflow["nodes"]}
    current = workflow["entry"]
    for _ in range(64):
        node = nodes[current]
        kind = node["kind"]
        if kind == "end":
            return text
        if kind == "agent":
            agent = Agent(name=node.get("name") or node["id"],
                          instructions=node.get("instructions", ""), model=node["model"],
                          model_settings=ModelSettings(store=False))
            text = str((await Runner.run(agent, text)).final_output)
        elif kind == "transform":
            template = node.get("instructions", "")
            if len(template) + template.count("{{input}}") * (len(text) - 9) > 1048576:
                raise ValueError("Transform too large")
            text = template.replace("{{input}}", text)
        if len(text) > 1048576:
            raise ValueError("Output too large")
        current = node["otherwise"] if kind == "condition" and node.get("match", "") not in text else node["next"]
    raise ValueError("Workflow exceeded 64 steps")

if __name__ == "__main__":
    print(asyncio.run(run(input("Input: "))))
"""
    )
