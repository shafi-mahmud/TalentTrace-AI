"""Synthetic live integration helper; separate invocations prove restart/resume.

Run from backend: python tests/checkpoint_resume_worker.py pause|resume <thread-id>
Requires the separately provisioned checkpoint database and explicit setup.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from app.db.checkpointer import open_checkpointer
from app.db.workflow_threads import WorkflowThread


class State(TypedDict, total=False):
    prepared: bool
    approved: bool
    finished: bool


def prepare(state):
    return {"prepared": True}


def human_pause(state):
    approved = interrupt("Synthetic approval required")
    if approved is not True:
        raise ValueError("Synthetic approval must be true")
    return {"approved": True}


def finish(state):
    return {"finished": True}


async def verify(action, thread_id):
    thread = WorkflowThread.from_thread_id(thread_id)
    config = {"configurable": {"thread_id": thread.thread_id}}
    async with open_checkpointer() as saver:
        builder = StateGraph(State)
        builder.add_node("prepare", prepare)
        builder.add_node("human_pause", human_pause)
        builder.add_node("finish", finish)
        builder.add_edge(START, "prepare")
        builder.add_edge("prepare", "human_pause")
        builder.add_edge("human_pause", "finish")
        builder.add_edge("finish", END)
        graph = builder.compile(checkpointer=saver)
        if action == "pause":
            result = await graph.ainvoke({}, config)
            snapshot = await graph.aget_state(config)
            assert result["__interrupt__"]
            assert snapshot.values == {"prepared": True}
            assert snapshot.next == ("human_pause",)
            assert await saver.aget_tuple(config) is not None
        elif action == "resume":
            snapshot = await graph.aget_state(config)
            assert snapshot.values == {"prepared": True}
            assert snapshot.next == ("human_pause",)
            result = await graph.ainvoke(Command(resume=True), config)
            assert result == {"prepared": True, "approved": True, "finished": True}
            final = await graph.aget_state(config)
            assert final.values == result and final.next == ()
        else:
            raise ValueError("Unknown proof action")


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError("Invalid proof arguments")
        with open(os.devnull, "w") as sink:
            from contextlib import redirect_stdout, redirect_stderr
            with redirect_stdout(sink), redirect_stderr(sink):
                asyncio.run(verify(sys.argv[1], sys.argv[2]), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
    except Exception:
        print("Checkpoint process proof failed; details withheld.")
        return 1
    print(f"Checkpoint {sys.argv[1]} proof passed. process_id={os.getpid()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
