"""Private Unix socket transport, shared by the dashboard and recovery broker."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import socket
import stat


def broker_socket(home: Path) -> Path | None:
    if os.name == "nt":
        return None
    # Keep well below macOS's 104-byte sockaddr_un limit even for long homes.
    digest = hashlib.sha256(str(Path(home).resolve()).encode()).hexdigest()[:24]
    return Path("/tmp").resolve() / f"utk-ipc-{os.getuid()}" / f"{digest}.sock"


def bind_broker_socket(home: Path):
    path = broker_socket(home)
    if path is None:
        return None
    path.parent.mkdir(mode=0o700, exist_ok=True)
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("UTK socket directory must be private and owned by this user")
    try:
        old = path.lstat()
    except FileNotFoundError:
        old = None
    if old:
        if not stat.S_ISSOCK(old.st_mode) or old.st_uid != os.getuid():
            raise PermissionError("Refusing to replace a non-owned socket path")
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise OSError("UTK broker socket already active")
    listener = socket.socket(socket.AF_UNIX)
    try:
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(128)
        return listener
    except BaseException:
        listener.close()
        raise


def serve():
    """One app instance/vault serves TCP and UDS; never fork a second vault."""
    import uvicorn
    from .config import Settings, default_home

    home = default_home()
    settings = Settings.load(home)
    listeners = []
    local = None
    local_inode = None
    path = broker_socket(home)

    def unlink_owned_socket():
        if path and local_inode:
            try:
                if path.lstat().st_ino == local_inode:
                    path.unlink()
            except FileNotFoundError:
                pass

    class LocalServer(uvicorn.Server):
        async def shutdown(self, sockets=None):
            try:
                await super().shutdown(sockets=sockets)
            finally:
                # Uvicorn can re-raise SIGTERM after graceful shutdown, before
                # the caller's finally block gets a chance to run.
                unlink_owned_socket()
    try:
        tcp = socket.socket(socket.AF_INET6 if ":" in settings.host else socket.AF_INET)
        listeners.append(tcp)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind((settings.dashboard_host, settings.dashboard_port))
        tcp.listen(128)
        local = bind_broker_socket(home)
        if local:
            listeners.append(local)
            local_inode = path.stat().st_ino
        LocalServer(uvicorn.Config("ultratokenkiller.service:app", log_level="warning", proxy_headers=False)).run(sockets=listeners)
    finally:
        for listener in listeners:
            listener.close()
        unlink_owned_socket()


if __name__ == "__main__":
    serve()
