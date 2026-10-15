import os
import sys

# The engine lives inside the skill folder, so the skill is self-contained when copied into a CLI.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "handoff", "scripts"))
