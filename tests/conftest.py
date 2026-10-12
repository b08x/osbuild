import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from intent_helpers import EXAMPLES, generate, tmpdir  # noqa: E402


@pytest.fixture(scope="session")
def generated():
    """{example stem: Generated} for every profiles/examples/ intent, generated once."""
    base = tmpdir()
    yield {p.stem: generate(p, base / p.stem) for p in EXAMPLES}
    shutil.rmtree(base, ignore_errors=True)
