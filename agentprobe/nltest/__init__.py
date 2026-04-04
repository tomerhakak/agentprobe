"""NLTest — Natural Language Test Writer.

Write agent tests in plain English. AgentProbe translates them to
executable test code with proper assertions.

Free tier feature — no Pro upgrade required.
"""

from agentprobe.nltest.generator import NLTestGenerator, GeneratedTest

__all__ = ["NLTestGenerator", "GeneratedTest"]
