"""Build a secret-free archive containing one top-level ``vivi-agent`` folder."""

from __future__ import annotations

import argparse
import importlib.util
import zipfile
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PACKAGE_ROOT.parent / "vivi-agent.zip"
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
}
EXCLUDED_FILES = {".env", ".coverage"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def _load_verifier():
    path = PACKAGE_ROOT / "scripts" / "verify_package.py"
    spec = importlib.util.spec_from_file_location("vivi_agent_package_verifier", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load verifier: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_package


def _included(path: Path, output: Path) -> bool:
    relative = path.relative_to(PACKAGE_ROOT)
    if path.resolve() == output.resolve():
        return False
    if any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in relative.parts[:-1]):
        return False
    if path.name in EXCLUDED_FILES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return True


def build_archive(output: Path) -> tuple[Path, int]:
    _load_verifier()()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in PACKAGE_ROOT.rglob("*") if path.is_file() and _included(path, output))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, Path(PACKAGE_ROOT.name) / path.relative_to(PACKAGE_ROOT))
    return output, len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output, file_count = build_archive(args.output)
    print(f"Built {output} with {file_count} files")


if __name__ == "__main__":
    main()
