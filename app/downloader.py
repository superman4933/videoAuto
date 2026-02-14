import hashlib
import shutil
from pathlib import Path
from urllib.parse import urlparse

import requests


class AssetDownloader:
    def __init__(self, cache_root: Path, timeout_sec: int = 30):
        self.cache_root = cache_root
        self.timeout_sec = timeout_sec
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def fetch(self, source: str, subdir: str) -> Path:
        if not source:
            raise ValueError("source must not be empty")
        target_dir = self.cache_root / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return self._download_http(source, target_dir)
        return self._copy_local(source, target_dir)

    def _download_http(self, url: str, target_dir: Path) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        ext = Path(urlparse(url).path).suffix or ".bin"
        target = target_dir / f"{digest}{ext}"
        if target.exists():
            return target

        response = requests.get(url, timeout=self.timeout_sec, stream=True)
        response.raise_for_status()
        with target.open("wb") as fp:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    fp.write(chunk)
        return target

    def _copy_local(self, source: str, target_dir: Path) -> Path:
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = Path.cwd() / source_path
        if not source_path.exists():
            raise FileNotFoundError(f"Local source not found: {source_path}")
        digest = hashlib.sha256(str(source_path).encode("utf-8")).hexdigest()[:16]
        ext = source_path.suffix or ".bin"
        target = target_dir / f"{digest}{ext}"
        if target.exists():
            return target
        shutil.copy2(source_path, target)
        return target
