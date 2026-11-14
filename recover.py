#!/usr/bin/env python3
"""RC4 crash-safe snapshot seal, inspection and explicit local restoration.

Only targets OPENHTPC-owned paths in the calling HOME. No media paths, no
network, no sudo, no deployment. --restore is deliberately never automatic.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile


def hash_content(path: pathlib.Path) -> str:
    if path.is_symlink():
        return "link:" + hashlib.sha256(os.readlink(path).encode()).hexdigest()
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return "file:" + h.hexdigest()


def snapshot_files(root: pathlib.Path) -> dict[str, str]:
    listing: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or path.is_file():
            listing[rel] = hash_content(path)
        elif not path.is_dir():
            raise ValueError("unsupported snapshot object: " + rel)
    return listing


def atomic_json(path: pathlib.Path, data: dict) -> None:
    temporary = path.with_name(".snapshot-seal-incomplete")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def fsync_snapshot_tree(root: pathlib.Path) -> None:
    # The seal must never reach durable storage ahead of the copied bytes.
    # Reject special files; sync every regular file and all enclosing dirs.
    directories = [root]
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue  # symlink target string is captured in signed inventory
        if path.is_dir():
            directories.append(path)
        elif path.is_file():
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        else:
            raise ValueError("unsupported snapshot filesystem object")
    for path in sorted(directories, key=lambda x: len(x.parts), reverse=True):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def fsync_dir(path: pathlib.Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def seal_restored_targets(home: pathlib.Path, paths: list[pathlib.Path]) -> None:
    # Sync every recovered file and directory before releasing the orphan guard.
    directories: set[pathlib.Path] = set()
    for path in paths:
        if path.is_dir() and not path.is_symlink():
            fsync_snapshot_tree(path)
        elif path.is_file() and not path.is_symlink():
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try: os.fsync(fd)
            finally: os.close(fd)
        for parent in path.parents:
            if parent == home.parent:break
            if parent.is_dir() and not parent.is_symlink():directories.add(parent)
    for parent in sorted(directories,key=lambda x:len(x.parts),reverse=True):
        fsync_dir(parent)


def validate_restorable_symlinks(snapshot: pathlib.Path, home: pathlib.Path) -> None:
    # Snapshot symlinks are copied, never dereferenced. Reject even creating a
    # managed link that would escape HOME when a future app follows it.
    home_real=home.resolve(strict=True)
    bindings=[(snapshot / "installed",home / ".local/lib/openhtpc")]
    targets=expected_paths(home)
    for i,entry in enumerate(targets):
        group=("legacy" if i<3 else "external" if i<12 else "runtime")
        slot=i if i<3 else i-3 if i<12 else i-12
        bindings.append((snapshot/group/str(slot),entry))
    for src,target in bindings:
        if src.is_symlink():
            link=pathlib.Path(os.readlink(src))
            dest=(target.parent / link).resolve(strict=False) if not link.is_absolute() else link.resolve(strict=False)
            if not dest.is_relative_to(home_real):raise ValueError("snapshot symlink outside HOME")
        if src.is_dir() and not src.is_symlink():
            for child in src.rglob("*"):
                if not child.is_symlink():continue
                rel=child.relative_to(src)
                target_at=target/rel
                link=pathlib.Path(os.readlink(child))
                dest=(target_at.parent / link).resolve(strict=False) if not link.is_absolute() else link.resolve(strict=False)
                if not dest.is_relative_to(home_real):raise ValueError("snapshot child symlink outside HOME")


def seal(snapshot: pathlib.Path, home: pathlib.Path) -> None:
    expected = home / ".local/state/openhtpc"
    if snapshot.parent != expected or not snapshot.name.startswith("upgrade-rollback."):
        raise ValueError("refusing snapshot outside exact HOME state path")
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("missing/unsafe snapshot")
    if (snapshot / "seal.json").exists():
        raise ValueError("already sealed")
    validate_restorable_symlinks(snapshot,home)
    contents = snapshot_files(snapshot)
    if not (snapshot / "legacy").is_dir() or not (snapshot / "external").is_dir() or not (snapshot / "runtime").is_dir():
        raise ValueError("incomplete snapshot directories")
    had_install = (snapshot / "installed").is_dir()
    if had_install and not (snapshot / "installed/VERSION").is_file():
        raise ValueError("installed snapshot incomplete: VERSION missing")
    fsync_snapshot_tree(snapshot)
    # Persist the parent directory entry: mktemp created the snapshot directory
    # before this helper was invoked; its name must also survive sudden power loss.
    fsync_dir(snapshot.parent)
    atomic_json(snapshot / "seal.json", {"schema": "openhtpc-rc4-recovery-v2", "had_install": had_install,
                                         "xdg_data_home": str(pathlib.Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share"))).absolute()),
                                         "files": contents})
    print("OPENHTPC_SNAPSHOT_SEALED", len(contents), "files")


def expected_paths(home: pathlib.Path) -> list[pathlib.Path]:
    return [
        home / ".config/openhtpc/media-browser.ini",
        home / ".config/openhtpc/media-browser-paths.json",
        home / ".local/state/openhtpc/media-model.json",
        home / ".local/bin/openhtpc-builder",
        home / ".local/bin/openhtpc-player-test",
        home / ".local/bin/openhtpc-session-start",
        home / ".local/bin/openhtpc-media-browser",
        home / ".local/bin/openhtpc",
        home / ".local/bin/openhtpc-validator",
        home / ".config/autostart/openhtpc.desktop",
        home / ".config/autostart/openhtpc-flex.desktop",
        pathlib.Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share"))) / "applications/openhtpc.desktop",
        home / ".config/openhtpc/profile.json",
        home / ".config/openhtpc/runtime",
        home / ".local/state/openhtpc/capability-validation.json",
    ]


def ensure_safe_target(home: pathlib.Path, path: pathlib.Path) -> None:
    if home.is_symlink() or not path.is_relative_to(home):
        raise ValueError("unsafe HOME or target")
    for ancestor in (path, *path.parents):
        if ancestor == home.parent:
            break
        if ancestor.is_symlink():
            if ancestor != path:
                raise ValueError("symlinked ancestor: " + str(ancestor))
            # The final target may be a managed symlink and is safe to unlink.
    if path.is_dir() and not path.is_symlink():
        return


def load_snapshot(snapshot: pathlib.Path, home: pathlib.Path) -> dict:
    if not snapshot.is_dir() or snapshot.is_symlink() or not snapshot.parent == home / ".local/state/openhtpc":
        raise ValueError("unsafe snapshot directory")
    meta = snapshot / "seal.json"
    if not meta.is_file() or meta.is_symlink():
        raise ValueError("incomplete snapshot: seal absent")
    doc = json.loads(meta.read_text())
    if doc.get("schema") != "openhtpc-rc4-recovery-v2" or not isinstance(doc.get("had_install"), bool):
        raise ValueError("invalid recovery seal schema")
    expected_xdg=str(pathlib.Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share"))).absolute())
    if doc.get("xdg_data_home") != expected_xdg:
        raise ValueError("XDG data path changed after snapshot; recovery refused")
    validate_restorable_symlinks(snapshot,home)
    expected = doc.get("files")
    if not isinstance(expected, dict) or not all(isinstance(k, str) and isinstance(v, str) and '..' not in pathlib.PurePosixPath(k).parts for k,v in expected.items()):
        raise ValueError("invalid recovery inventory")
    observed = snapshot_files(snapshot)
    observed.pop("seal.json", None)
    if observed != expected:
        raise ValueError("snapshot content mismatch: refuses unsafe restore")
    if (snapshot / "installed").is_dir() != doc["had_install"]:
        raise ValueError("installed snapshot state mismatch")
    return doc


def recover(snapshot: pathlib.Path, home: pathlib.Path, meta: dict) -> None:
    install = home / ".local/lib/openhtpc"
    targets = expected_paths(home)
    for entry in [install, *targets]:
        ensure_safe_target(home, entry)
    # Fail closed when an appliance session claims RUNNING, even if stale lock
    # files would let us proceed; a remote recovery must never stop live Flex.
    session = home / ".local/state/openhtpc/runtime-session.json"
    if session.exists():
        try:
            state = json.loads(session.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ValueError("unreadable runtime session state") from exc
        if not isinstance(state, dict) or state.get("state") != "STOPPED":
            raise ValueError("active or unsafe OPENHTPC runtime session; recovery refused")
    # A sealed and checked snapshot is recovered only when no playback locks held.
    import contextlib
    with contextlib.ExitStack() as stack:
        for name in ("playback-active.lock", "play-dvd.lock"):
            lockpath = home / ".local/state/openhtpc" / name
            handle = stack.enter_context(lockpath.open("a+"))
            try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise ValueError("active playback lock " + name) from exc
        # Prepare install copy entirely before replacing any previous installed tree.
        parent = install.parent
        parent.mkdir(parents=True, exist_ok=True)
        prepared = None
        if meta["had_install"]:
            prepared = pathlib.Path(tempfile.mkdtemp(prefix=".openhtpc-recover-stage-", dir=parent))
            shutil.copytree(snapshot / "installed", prepared / "restored", symlinks=True)
        if install.is_symlink(): raise ValueError("installed symlink blocked")
        if install.exists():
            quarantine = pathlib.Path(tempfile.mkdtemp(prefix=".openhtpc-damaged-",dir=parent))
            quarantine.rmdir()
            os.replace(install, quarantine)
            print("OPENHTPC_QUARANTINED_DAMAGED_INSTALL", quarantine)
        if prepared is not None:
            os.replace(prepared / "restored", install)
            prepared.rmdir()
        groups = ["legacy"]*3 + ["external"]*9 + ["runtime"]*3
        for index,(entry,group) in enumerate(zip(targets,groups)):
            source = snapshot / group / str(index if group=="legacy" else index-3 if group=="external" else index-12)
            if entry.is_symlink() or entry.is_file(): entry.unlink()
            elif entry.is_dir(): shutil.rmtree(entry)
            if source.is_symlink() or source.exists():
                entry.parent.mkdir(parents=True,exist_ok=True)
                if source.is_symlink(): entry.symlink_to(os.readlink(source))
                elif source.is_dir(): shutil.copytree(source,entry,symlinks=True)
                else: shutil.copy2(source,entry)
        seal_restored_targets(home,[install,*targets])
        recovered = snapshot.with_name("upgrade-recovered." + snapshot.name.removeprefix("upgrade-rollback."))
        if recovered.exists():raise ValueError("existing recovered backup destination")
        os.replace(snapshot,recovered)
        fsync_dir(recovered.parent)
        print("OPENHTPC_RECOVERY_DONE; backup kept for operator:", recovered)


def main() -> int:
    parser=argparse.ArgumentParser()
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--seal", type=pathlib.Path)
    actions.add_argument("--check-paths", action="store_true")
    actions.add_argument("--inspect", action="store_true")
    actions.add_argument("--restore", action="store_true")
    args=parser.parse_args()
    home=pathlib.Path.home().absolute()
    try:
        if home.is_symlink():raise ValueError("symlinked HOME")
        if args.seal is not None:
            seal(args.seal.absolute(),home)
            return 0
        if args.check_paths:
            for path in [home / ".local/lib/openhtpc", *expected_paths(home)]:
                ensure_safe_target(home, path)
            print("OPENHTPC_HOME_PATHS_SAFE")
            return 0
        folder=home / ".local/state/openhtpc"
        snapshots=sorted(folder.glob("upgrade-rollback.*"))
        if len(snapshots)!=1:
            raise ValueError("expected exactly ONE rollback snapshot, got " + str(len(snapshots)))
        snapshot=snapshots[0]
        doc=load_snapshot(snapshot,home)
        print("OPENHTPC_SNAPSHOT_VALID",len(doc["files"]),"files",snapshot)
        if args.restore:recover(snapshot,home,doc)
        return 0
    except (OSError,ValueError,RuntimeError,json.JSONDecodeError) as exc:
        print("OPENHTPC_RECOVERY_REFUSED: "+str(exc),file=sys.stderr)
        return 44


if __name__=="__main__":
    raise SystemExit(main())
