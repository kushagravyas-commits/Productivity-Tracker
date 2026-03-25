import os
import sys
import time
import uuid
from datetime import datetime

import requests


POLL_INTERVAL_SECONDS = 5
DEFAULT_API_BASE_URL = "http://127.0.0.1:8080"


def log(msg: str) -> None:
    print(f"[TrackFlowDaVinci] {msg}")


def local_naive_iso() -> str:
    # Send local device time without timezone offset (matches other context producers).
    return datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def get_machine_guid() -> str:
    if sys.platform == "darwin":
        try:
            cmd = (
                "ioreg -rd1 -c IOPlatformExpertDevice | "
                "awk '/IOPlatformUUID/ { split($0, line, \"\\\"\"); printf(\"%s\", line[4]); }'"
            )
            out = os.popen(cmd).read().strip()
            if out:
                return out
        except Exception:
            pass

    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return str(guid)
        except Exception:
            pass

    return str(uuid.getnode())


def resolve_script_api_root() -> str | None:
    # Official docs: resolve scripting API location defaults vary by OS.
    # https://wiki.dvresolve.com/developer-docs/scripting-api
    api_root = os.getenv("RESOLVE_SCRIPT_API")
    if api_root:
        return api_root

    if sys.platform == "darwin":
        return "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"

    if sys.platform == "win32":
        program_data = os.getenv("PROGRAMDATA", r"C:\ProgramData")
        return os.path.join(
            program_data,
            "Blackmagic Design",
            "DaVinci Resolve",
            "Support",
            "Developer",
            "Scripting",
        )

    return None


def configure_resolve_modules_from_docs() -> None:
    api_root = resolve_script_api_root()
    if not api_root:
        return

    modules_dir = os.path.join(api_root, "Modules")
    if os.path.isdir(modules_dir) and modules_dir not in sys.path:
        sys.path.insert(0, modules_dir)

    # Best-effort set RESOLVE_SCRIPT_LIB based on official docs (only if the file exists).
    # This mirrors the documented environment variable approach for Resolve scripting.
    if not os.getenv("RESOLVE_SCRIPT_LIB"):
        if sys.platform == "darwin":
            candidate = (
                "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
            )
        elif sys.platform == "win32":
            candidate = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
        else:
            candidate = ""
        if candidate and os.path.exists(candidate):
            os.environ["RESOLVE_SCRIPT_LIB"] = candidate


def get_resolve_handle():
    configure_resolve_modules_from_docs()
    try:
        import DaVinciResolveScript as dvr_script  # type: ignore

        return dvr_script.scriptapp("Resolve")
    except Exception as e:
        log(f"Resolve scripting import failed: {e}")
        return None


def collect_app_context(resolve_handle: object) -> dict:
    project_manager = resolve_handle.GetProjectManager()
    project = project_manager.GetCurrentProject()

    if not project:
        return {
            "app_name": "DaVinci Resolve",
            "active_file_name": None,
            "active_file_path": None,
            "active_sequence": None,
            "captured_at": local_naive_iso(),
        }

    project_name = project.GetName()
    timeline = project.GetCurrentTimeline()
    timeline_name = timeline.GetName() if timeline else None

    return {
        "app_name": "DaVinci Resolve",
        "active_file_name": project_name,
        "active_file_path": f"Project: {project_name}" if project_name else None,
        "active_sequence": timeline_name,
        "captured_at": local_naive_iso(),
    }


def post_app_context(api_base_url: str, machine_guid: str, payload: dict) -> None:
    url = f"{api_base_url.rstrip('/')}/api/v1/context/app"
    headers = {"X-Machine-GUID": machine_guid, "Content-Type": "application/json"}
    res = requests.post(url, json=payload, headers=headers, timeout=5)
    if res.status_code == 200:
        log(
            f"Posted app context: project={payload.get('active_file_name')} timeline={payload.get('active_sequence')}"
        )
    else:
        log(f"App context post failed: {res.status_code} body={res.text[:200]}")


def main() -> None:
    api_base_url = os.getenv("TRACKER_API_BASE_URL", DEFAULT_API_BASE_URL)
    machine_guid = get_machine_guid()
    log(f"Starting DaVinci Resolve Productivity Tracker. machine_guid={machine_guid}")
    log(f"Posting to backend: {api_base_url}/api/v1/context/app")
    log(f"Resolve script API root: {resolve_script_api_root()}")

    last_resolve_unavailable_at = 0.0

    while True:
        resolve_handle = None
        try:
            resolve_handle = get_resolve_handle()
            if not resolve_handle:
                now = time.time()
                if now - last_resolve_unavailable_at > 20:
                    log(
                        "Resolve scripting handle not available (Resolve running + scripting access must be enabled)."
                    )
                    last_resolve_unavailable_at = now
                time.sleep(POLL_INTERVAL_SECONDS * 2)
                continue

            payload = collect_app_context(resolve_handle)
            post_app_context(api_base_url, machine_guid, payload)
        except Exception as e:
            log(f"Loop error: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
