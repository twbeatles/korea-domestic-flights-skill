from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SOURCE_REPO_DIRNAME = "Scraping-flight-information"
SOURCE_REPO_ENV_VARS = ("KDF_SOURCE_REPO", "SCRAPING_FLIGHT_INFORMATION_REPO")
WORKSPACE_ENV_VARS = ("KDF_WORKSPACE",)


class SourceRepoError(RuntimeError):
    """Raised when the runtime source repository cannot be used."""


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    output: list[Path] = []
    for path in paths:
        key = str(path.resolve(strict=False)).lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(path)
    return output


def source_repo_candidates(repo_path: str | Path | None = None, *, base_dir: str | Path | None = None) -> list[Path]:
    if repo_path:
        return [Path(repo_path).expanduser().resolve(strict=False)]
    candidates: list[Path] = []
    for env_var in SOURCE_REPO_ENV_VARS:
        raw = os.environ.get(env_var)
        if raw:
            candidates.append(Path(raw).expanduser().resolve(strict=False))

    bases: list[Path] = [Path.cwd()]
    if base_dir:
        bases.append(Path(base_dir).expanduser().resolve(strict=False))
    for env_var in WORKSPACE_ENV_VARS:
        raw = os.environ.get(env_var)
        if raw:
            bases.append(Path(raw).expanduser().resolve(strict=False))
    package_root = Path(__file__).resolve().parents[2]
    bases.extend([package_root, *package_root.parents[:4], *Path.cwd().parents[:4]])
    for base in bases:
        candidates.append(base / "tmp" / SOURCE_REPO_DIRNAME)
        candidates.append(base / SOURCE_REPO_DIRNAME)
        if base.name == "openclaw-korea-domestic-flights":
            candidates.append(base.parent / SOURCE_REPO_DIRNAME)
    return _unique_paths(candidates)


def resolve_source_repo(repo_path: str | Path | None = None) -> Path:
    candidates = source_repo_candidates(repo_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = "\n".join(f"- {candidate}" for candidate in candidates)
    raise FileNotFoundError(f"Source repository clone not found. Searched:\n{searched}")


@dataclass
class SourceHealth:
    repo_path: str
    exists: bool
    required_files: dict[str, bool]
    import_checked: bool = False
    import_ok: bool = False
    import_error: str | None = None

    @property
    def ok(self) -> bool:
        static_ok = self.exists and all(self.required_files.values())
        return static_ok and (self.import_ok if self.import_checked else True)

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "exists": self.exists,
            "required_files": self.required_files,
            "import_checked": self.import_checked,
            "import_ok": self.import_ok,
            "import_error": self.import_error,
            "ok": self.ok,
        }


def doctor(repo_path: str | Path | None = None, *, import_check: bool = False) -> SourceHealth:
    resolved = resolve_source_repo(repo_path)
    required = {
        "scraping/searcher.py": (resolved / "scraping" / "searcher.py").exists(),
        "scraping/parallel.py": (resolved / "scraping" / "parallel.py").exists(),
        "scraping/models.py": (resolved / "scraping" / "models.py").exists(),
        "scraper_config.py": (resolved / "scraper_config.py").exists(),
    }
    health = SourceHealth(str(resolved), resolved.exists(), required, import_checked=import_check)
    if import_check:
        try:
            adapter = FlightSourceAdapter(repo_path=resolved)
            adapter.import_searchers()
            health.import_ok = True
        except Exception as exc:
            health.import_error = str(exc)
    return health


class FlightSourceAdapter:
    """Adapter around the external Scraping-flight-information runtime."""

    def __init__(self, repo_path: str | Path | None = None):
        self.repo_path = resolve_source_repo(repo_path)

    def _ensure_path(self) -> None:
        path = str(self.repo_path)
        if path not in sys.path:
            sys.path.insert(0, path)

    def import_searchers(self):
        self._ensure_path()
        try:
            from scraping.parallel import ParallelSearcher
            from scraping.searcher import FlightSearcher
        except Exception as exc:
            raise SourceRepoError(f"Failed to import source searchers from {self.repo_path}: {exc}") from exc
        return FlightSearcher, ParallelSearcher

    def search(
        self,
        *,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        adults: int = 1,
        cabin_class: str = "ECONOMY",
        max_results: int = 1000,
        background_mode: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list:
        FlightSearcher, _ = self.import_searchers()
        searcher = FlightSearcher()
        try:
            return searcher.search(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                adults=adults,
                cabin_class=cabin_class,
                max_results=max_results,
                progress_callback=progress_callback,
                background_mode=background_mode,
            )
        finally:
            close_fn = getattr(searcher, "close", None)
            if callable(close_fn):
                close_fn()

    def broad_date_range(
        self,
        *,
        origin: str,
        destination: str,
        dates: list[str],
        return_offset: int = 0,
        adults: int = 1,
        cabin_class: str = "ECONOMY",
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, tuple[int, str]]:
        _, ParallelSearcher = self.import_searchers()
        searcher = ParallelSearcher()
        try:
            return searcher.search_date_range(
                origin=origin,
                destination=destination,
                dates=dates,
                return_offset=return_offset,
                adults=adults,
                cabin_class=cabin_class,
                progress_callback=progress_callback,
            )
        finally:
            close_fn = getattr(searcher, "close", None)
            if callable(close_fn):
                close_fn()
