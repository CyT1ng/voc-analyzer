"""Agentic gathering loop: repeat search→scrape→integrate until enough, then hand off."""

from voc_analyzer.gather.loop import GatherResult, run_gather_loop

__all__ = ["GatherResult", "run_gather_loop"]
