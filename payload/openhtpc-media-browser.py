#!/usr/bin/env python3
"""Direct, non-indexing local media navigation using Flex menus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile


def load_theme(install: pathlib.Path):
    import importlib.util
    path = install / "openhtpc-theme.py"
    if not path.is_file():
        path = pathlib.Path(__file__).with_name("openhtpc-theme.py")
    spec = importlib.util.spec_from_file_location("media_theme", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"}


def path_id(path: pathlib.Path) -> str:
    return hashlib.blake2s(os.fsencode(path), digest_size=12).hexdigest()


def source_id(path: pathlib.Path) -> str:
    return hashlib.blake2s(os.fsencode(path), digest_size=8).hexdigest()


def resolve_path_id(value: str, mapping: dict[str, str]) -> pathlib.Path:
    if not isinstance(value, str) or len(value) != 24 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("Identifiant de navigation média invalide.")
    raw = mapping.get(value)
    if not isinstance(raw, str) or not pathlib.Path(raw).is_absolute():
        raise ValueError("Le contexte de navigation média a expiré.")
    return pathlib.Path(raw)


def configured_sources(home: pathlib.Path) -> list[pathlib.Path]:
    try:
        config = json.loads((home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8"))
        values = config["local_media_sources"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Configuration des médias locaux invalide.") from exc
    if not isinstance(values, list):
        raise ValueError("Configuration des médias locaux invalide.")
    return [pathlib.Path(value) for value in values if isinstance(value, str) and pathlib.Path(value).is_absolute()]


def within(path: pathlib.Path, roots: list[pathlib.Path]) -> bool:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return any(resolved == root.resolve() or root.resolve() in resolved.parents for root in roots if root.exists())


def source_for(path: pathlib.Path, roots: list[pathlib.Path]) -> pathlib.Path | None:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    matches = [root.resolve() for root in roots if root.exists() and (resolved == root.resolve() or root.resolve() in resolved.parents)]
    return max(matches, key=lambda root: len(root.parts)) if matches else None


def write_playback_context(home: pathlib.Path, source: pathlib.Path, folder: pathlib.Path, selected: pathlib.Path) -> pathlib.Path:
    target = home / ".config/openhtpc/media-browser-context.json"
    data = {"schema": 1, "source": str(source), "current_directory": str(folder), "selected_item": selected.name}
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return target


def write_generic_context(home: pathlib.Path, source: pathlib.Path, folder: pathlib.Path, selected: pathlib.Path) -> pathlib.Path:
    target = home / ".local/state/openhtpc/playback-context.json"
    data = {"schema": 1, "kind": "media_browser", "source": str(source), "folder": str(folder), "selected_item": selected.name}
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, sort_keys=True); stream.write("\n")
        os.chmod(temporary, 0o600); os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return target


def restored_folder(home: pathlib.Path, roots: list[pathlib.Path]) -> tuple[pathlib.Path, str | None]:
    try:
        data = json.loads((home / ".config/openhtpc/media-browser-context.json").read_text(encoding="utf-8"))
        source = pathlib.Path(data["source"])
        folder = pathlib.Path(data["current_directory"])
        selected = data.get("selected_item")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Aucun contexte média valide à restaurer.") from exc
    if source not in roots or not within(folder, [source]) or not folder.is_dir():
        raise ValueError("Le dossier média précédent n'est plus disponible.")
    return folder, selected if isinstance(selected, str) else None


def directory_entries(path: pathlib.Path) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        raise ValueError(f"Source indisponible : {path}") from exc
    directories = sorted((item for item in entries if item.is_dir()), key=lambda item: item.name.casefold())
    videos = sorted((item for item in entries if item.is_file() and item.suffix.casefold() in VIDEO_EXTENSIONS), key=lambda item: item.name.casefold())
    return directories, videos


def clean_label(value: str) -> str:
    return value.replace(";", "—").replace("\n", " ").replace("\r", " ")


def write_menu(target: pathlib.Path, home: pathlib.Path, current: pathlib.Path | None, roots: list[pathlib.Path], scale: dict[str, int]) -> None:
    install = home / ".local/lib/openhtpc"
    browser = home / ".local/bin/openhtpc-media-browser"
    session = install / "openhtpc-session-start"
    icon = install / "flex/assets/icons/drive-empty.png"
    font = install / "flex/assets/fonts/OpenSans-Regular.ttf"
    theme = load_theme(install)
    commands = []
    mapping = {}
    def reference(path: pathlib.Path) -> str:
        identifier = path_id(path)
        mapping[identifier] = str(path)
        return identifier
    if current is None:
        if roots:
            for root in roots:
                status = "" if root.is_dir() else " — indisponible"
                commands.append((clean_label(root.name or str(root)) + status, f":replace {shlex.quote(str(browser))} --open {reference(root)}"))
            commands.append(("RETOUR À OPENHTPC", f":replace {shlex.quote(str(session))}"))
    else:
        if not within(current, roots) or not current.is_dir():
            raise ValueError(f"Source indisponible : {current}")
        parent = current.parent
        parent_command = f":replace {shlex.quote(str(browser))}" if any(current.resolve() == root.resolve() for root in roots if root.exists()) else f":replace {shlex.quote(str(browser))} --open {reference(parent)}"
        commands.append(("RETOUR", parent_command))
        directories, videos = directory_entries(current)
        commands.extend(("DOSSIER — " + clean_label(item.name), f":replace {shlex.quote(str(browser))} --open {reference(item)}") for item in directories)
        commands.extend((clean_label(item.name), f"env OPENHTPC_FLEX_RETAINED=1 {shlex.quote(str(browser))} --play {reference(item)}") for item in videos)
    if not commands:
        commands.append(("AUCUN MÉDIA LOCAL CONFIGURÉ", shlex.quote(str(session))))
    back_command = commands[0][1] if current is not None else f":replace {shlex.quote(str(session))}"
    entries = "\n".join(f"Entry{i}={label};{icon};{command}" for i, (label, command) in enumerate(commands, 1))
    content = f"""[General]
DefaultMenu=Médias
VSync=true
OnLaunch=Blank
WrapEntries=true
ResetOnBack=true
MouseSelect=true
InhibitOSScreensaver=true
{theme.background_block(install, 62)}
[Layout]
MaxButtons=8
IconSize={scale['icon']}
IconSpacing=3%
VCenter=50%
{theme.title_block(font, scale['title'], scale['padding'])}
{theme.highlight_block()}
[Scroll Indicators]
Enabled=true
FillColor=#FFFFFF
OutlineSize=0
OutlineColor=#000000
Opacity=100%
[Clock]
Enabled=true
ShowDate=true
Alignment=Right
Font={font}
FontSize={scale['clock']}
FontColor=#FFFFFF
Shadows=false
Margin=4%
Opacity=100%
TimeFormat=24hr
DateFormat=Auto
IncludeWeekday=true
[Screensaver]
Enabled=false
[Hotkeys]
Hotkey1=#1B;{back_command}
Hotkey2=#08;{back_command}
[Gamepad]
Enabled=false
DeviceIndex=-1
LStickX-=:left
LStickX+=:right
ButtonA=:select
ButtonB=:back
ButtonDPadLeft=:left
ButtonDPadRight=:right
[Médias]
{entries}
"""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    state = target.with_name("media-browser-paths.json")
    fd, temporary = tempfile.mkstemp(prefix=state.name + ".", dir=state.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(mapping, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, state)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def show_error(message: str) -> None:
    if (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and subprocess.run(["sh", "-c", "command -v kdialog >/dev/null 2>&1"]).returncode == 0:
        subprocess.run(["kdialog", "--title", "OPENHTPC", "--error", message])
    else:
        print(f"[OPENHTPC] {message}", file=sys.stderr)


def flex_instances(install: pathlib.Path) -> tuple[int,list[int]]:
    try:
        result=subprocess.run(["pgrep","-f",f"^{re.escape(str(install/'flex/bin/flex-launcher'))}(?: |$)"],text=True,capture_output=True,timeout=2,check=False)
        pids=[int(value) for value in result.stdout.split() if value.isdigit()]
    except (OSError,subprocess.TimeoutExpired,ValueError):pids=[]
    return len(pids),pids


def write_action_state(home:pathlib.Path,**fields:object)->pathlib.Path:
    target=home/".local/state/openhtpc/media-action-last.json";target.parent.mkdir(parents=True,exist_ok=True)
    fields={"schema":1,"timestamp":__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),**fields}
    fd,temporary=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(fields,stream,ensure_ascii=False,sort_keys=True);stream.write("\n")
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return target


def runtime_event(install:pathlib.Path,event:str,**fields:object)->None:
    helper=install/"openhtpc-runtime.py"
    if helper.is_file() and os.access(helper,os.X_OK):
        command=[str(helper),"log","--component","media","--event",event]
        subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate",action="store_true")
    parser.add_argument("--generation")
    parser.add_argument("--source-id")
    parser.add_argument("--item-id")
    parser.add_argument("--item-type")
    parser.add_argument("--relative-path")
    args = parser.parse_args()
    home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
    count,pids=flex_instances(install)
    action=dict(media_action_seen=True,dispatcher_seen=False,current_page="MEDIA",model_generation=args.generation or "unknown",source_id=args.source_id or "unknown",item_id=args.item_id or "unknown",item_type=args.item_type or "unknown",path_resolved=False,path_absolute=False,file_exists=False,process_started=False,flex_instances=count,authoritative_flex_pid=pids[0] if len(pids)==1 else None,error_class="ACTION_VALIDATION_PENDING")
    write_action_state(home,**action);runtime_event(install,"MEDIA_ITEM_ACTIVATED")
    try:
        if not args.activate or args.item_type!="file":raise ValueError("ACTION_TYPE_INVALID")
        model=json.loads((home/".local/state/openhtpc/media-model.json").read_text(encoding="utf-8"))
        selected_model=model.get("models",{}).get(args.generation)
        if not isinstance(selected_model,dict):raise ValueError("STALE_MODEL_GENERATION")
        source=next((value for value in selected_model.get("sources",[]) if value.get("source_id")==args.source_id),None)
        if source is None:raise ValueError("SOURCE_ID_INVALID")
        relative=pathlib.PurePosixPath(args.relative_path or "")
        if relative.is_absolute() or not relative.parts or any(part in ("",".","..") for part in relative.parts):raise ValueError("RELATIVE_PATH_INVALID")
        expected=hashlib.blake2s(f"media:{args.source_id}:file:{relative.as_posix()}".encode("utf-8"),digest_size=12).hexdigest()
        if args.item_id!=expected:raise ValueError("ITEM_ID_INVALID")
        action.update(dispatcher_seen=True,error_class="NONE");write_action_state(home,**action);runtime_event(install,"FILE_DISPATCH_REQUEST")
        player=install/"openhtpc-play"
        os.execv(player,[str(player),"--source-id",args.source_id,"--relative-path",relative.as_posix(),"--model-generation",args.generation])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        action.update(error_class=str(exc) or "ACTION_INVALID");write_action_state(home,**action);show_error("Cette sélection média a expiré. Revenez à MEDIA puis réessayez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
