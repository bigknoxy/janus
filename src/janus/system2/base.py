"""System 2 contract: every generative engine produces raw text that the
patcher parses into PatchBlocks. The protocol is the seam (OCP/DIP)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class GenerativeEngineProtocol(Protocol):
    def generate_patch(self, prompt: str) -> str:
        """Given a fully-assembled surgical prompt, return raw model text.
        Parsing and validation are the patcher's job, never the client's."""
        ...
