import importlib.util
import sys
from pathlib import Path

import agent

# Temporary package redirect/proxy during T1 and T2 migration steps.
# Dynamically loads the legacy agent/tools.py file under agent.tools to keep the app working.
tools_path = Path(__file__).parent.parent / "tools.py"
spec = importlib.util.spec_from_file_location("agent.tools", str(tools_path))
module = importlib.util.module_from_spec(spec)
module.__path__ = [str(Path(__file__).parent)]
sys.modules["agent.tools"] = module
agent.tools = module
spec.loader.exec_module(module)

# Expose everything from tools.py in the package namespace
globals().update({k: v for k, v in module.__dict__.items() if not k.startswith("__")})
