"""Root conftest — adds the Architecture directory to sys.path so that
the stages/, utils/, tasks/, and knowledge_base/ packages are importable
when pytest is invoked from this directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
