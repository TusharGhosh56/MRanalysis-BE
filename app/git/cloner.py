import os
import shutil
import stat
from pathlib import Path

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

from git import Repo

from app.config import get_settings

settings = get_settings()


class GitCloneError(Exception):
    pass


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return

    def onexc(func, p, exc):
        if isinstance(exc, PermissionError):
            os.chmod(p, stat.S_IWUSR)
            func(p)
        else:
            raise exc

    shutil.rmtree(path, onexc=onexc)


class GitRepositoryCloner:
    def __init__(self, base_path: str | None = None) -> None:
        raw_path = base_path or settings.REPOS_BASE_PATH
        if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            raw_path = "/tmp/repos"
        self.base_path = Path(raw_path)

    def clone_path_for(self, owner: str, name: str) -> Path:
        return self.base_path / owner / name

    def _sync_existing(self, target: Path, url: str) -> None:
        repo = Repo(str(target))
        try:
            with repo.config_writer() as cfg:
                cfg.set_value('remote "origin"', "url", url)
            origin = repo.remote("origin")
            origin.fetch(prune=True)
            origin.pull()
        finally:
            repo.close()

    def clone(self, *, url: str, owner: str, name: str) -> Path:
        target = self.clone_path_for(owner, name)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.base_path = Path("/tmp/repos")
            target = self.clone_path_for(owner, name)
            target.parent.mkdir(parents=True, exist_ok=True)

        if (target / ".git").is_dir():
            try:
                self._sync_existing(target, url)
                return target
            except Exception:
                _remove_tree(target)
        elif target.exists():
            _remove_tree(target)

        try:
            Repo.clone_from(
                url,
                str(target),
                multi_options=["--progress"],
            )
        except Exception as exc:
            _remove_tree(target)
            raise GitCloneError(str(exc)) from exc

        return target

    def remove_clone(self, clone_path: str) -> None:
        _remove_tree(Path(clone_path))