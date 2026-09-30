"""File access for a trusted local stdio client, limited to configured directories."""
from pathlib import Path, PureWindowsPath
import os
import stat
import tempfile

MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_EXPORT_BYTES = 100 * 1024 * 1024


class FileAccessError(ValueError):
    """An expected file failure with a message safe to return to a client."""


class LocalFiles:
    def __init__(self, data_dir: Path, output_dir: Path | None = None):
        try:
            self.data_dir = data_dir.resolve(strict=True)
            if not self.data_dir.is_dir():
                raise OSError
            # Create exports lazily so inspection also works with read-only data.
            self.output_dir = (output_dir or self.data_dir / "exports").resolve()
        except (OSError, ValueError, RuntimeError):
            raise FileAccessError("Data directory must be an existing readable directory.") from None

    def read_text(self, filename: str, extensions: set[str]) -> str:
        """Read a bounded UTF-8 regular file; never follow a link outside data_dir."""
        path = Path(filename)
        if (not filename or len(filename) > 1024 or "\x00" in filename
                or "\\" in filename or ":" in filename or path.is_absolute()
                or PureWindowsPath(filename).drive or ".." in path.parts):
            raise FileAccessError("Use a relative file path inside the data directory, with / separators and no '..'.")
        if path.suffix.lower() not in extensions:
            raise FileAccessError("Unsupported file type; expected " + ", ".join(sorted(extensions)) + ".")
        try:
            resolved = (self.data_dir / path).resolve(strict=True)
            if not resolved.is_relative_to(self.data_dir):
                raise FileAccessError("File must stay inside the configured data directory.")
            if not stat.S_ISREG(resolved.stat().st_mode):
                raise FileAccessError("Input must be a regular file.")
            # O_NONBLOCK prevents a replaced FIFO from hanging the server on POSIX.
            fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise FileAccessError("Input must be a regular file.")
                if info.st_size > MAX_FILE_BYTES:
                    raise FileAccessError("File exceeds the 40 MiB limit.")
                content = stream.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:
                raise FileAccessError("File exceeds the 40 MiB limit.")
            return content.decode("utf-8-sig")
        except FileAccessError:
            raise
        except UnicodeError:
            raise FileAccessError("Input must be UTF-8 text.") from None
        except (OSError, ValueError, RuntimeError):
            raise FileAccessError("File is missing or unreadable inside the data directory.") from None

    def export(self, content: str, suffix: str) -> tuple[Path, int]:
        """Create a unique export; callers cannot name or overwrite existing files."""
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_EXPORT_BYTES:
            raise FileAccessError("Export exceeds 100 MiB; use a smaller grid or fewer transitions.")
        path = None
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if self.output_dir.resolve(strict=True) != self.output_dir:
                raise FileAccessError("Export directory changed; restart the server with a trusted directory.")
            fd, name = tempfile.mkstemp(prefix="orbital-studio-", suffix=suffix, dir=self.output_dir)
            path = Path(name)
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
            return path, len(encoded)
        except (OSError, ValueError):
            if path is not None:
                path.unlink(missing_ok=True)
            raise FileAccessError("Could not write export in the configured output directory.") from None
