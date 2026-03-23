import os
import shutil
import subprocess
from pathlib import Path

# Configuration
APP_NAME = "TrackFlow"
ROOT_DIR = Path(__file__).parent.resolve()
DIST_DIR = ROOT_DIR / "dist_bin_mac"
FRONTEND_DIR = ROOT_DIR / "frontend"
BACKEND_DIR = ROOT_DIR / "backend"
AGENT_DIR = ROOT_DIR / "agent"
VSCODE_DIR = ROOT_DIR / "vscode-extension"
CHROME_DIR = ROOT_DIR / "chrome-extension"


def clean():
    print("Cleaning old builds...")
    for d in [BACKEND_DIR / "build", BACKEND_DIR / "dist",
              AGENT_DIR / "build", AGENT_DIR / "dist", BACKEND_DIR / "static",
              ROOT_DIR / "__pycache__", BACKEND_DIR / "app" / "__pycache__",
              BACKEND_DIR / "app" / "services" / "__pycache__"]:
        if d.exists():
            try:
                shutil.rmtree(d)
            except PermissionError:
                print(f"Warning: Cannot fully remove {d.name} (in use), skipping")
    
    if DIST_DIR.exists():
        for f in DIST_DIR.iterdir():
            try:
                f.unlink() if f.is_file() else shutil.rmtree(f)
            except PermissionError:
                print(f"Warning: Cannot remove {f.name} (in use)")
    
    for spec in list(AGENT_DIR.glob("*.spec")) + list(BACKEND_DIR.glob("*.spec")):
        spec.unlink()
    DIST_DIR.mkdir(exist_ok=True)

def build_frontend():
    print("\n--- Building Frontend ---")
    os.chdir(FRONTEND_DIR)
    subprocess.run("npm run build", shell=True, check=True)
    static_dest = BACKEND_DIR / "static"
    if static_dest.exists():
        shutil.rmtree(static_dest)
    shutil.copytree(FRONTEND_DIR / "dist", static_dest)
    os.chdir(ROOT_DIR)


def build_vscode_extension():
    print("\n--- Building VS Code Extension (VSIX) ---")
    os.chdir(VSCODE_DIR)
    if not (VSCODE_DIR / "node_modules").exists():
        subprocess.run("npm install", shell=True, check=True)
    subprocess.run("npm run package", shell=True, check=True)
    vsix = VSCODE_DIR / "trackflow-context-0.0.1.vsix"
    if not vsix.exists():
        raise FileNotFoundError(f"VSIX not found at {vsix}")
    shutil.copy(vsix, AGENT_DIR / "trackflow-context-0.0.1.vsix")
    print(f"Copied VSIX to {AGENT_DIR / 'trackflow-context-0.0.1.vsix'}")
    os.chdir(ROOT_DIR)

def build_backend():
    print("\n--- Packaging Backend (Admin Dashboard) ---")
    os.chdir(BACKEND_DIR)
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconsole",
        f"--name={APP_NAME}Server",
        # Use colon for path separator on macOS (data separator)
        "--add-data=static:static",
        "--add-data=.env:.",
        "--hidden-import=motor",
        "--hidden-import=motor.motor_asyncio",
        "--hidden-import=uvicorn",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=dns.resolver",
        "--hidden-import=dns.rdatatype",
        "--hidden-import=asyncpg",
        "--hidden-import=asyncpg.pgproto.pgproto",
        "app/main.py",
    ]
    subprocess.run(cmd, check=True)
    shutil.copy(Path("dist") / f"{APP_NAME}Server", DIST_DIR / f"{APP_NAME}Server")
    # Restore executable cross-platform permissions
    (DIST_DIR / f"{APP_NAME}Server").chmod(0o755)
    os.chdir(ROOT_DIR)


def build_agent():
    print("\n--- Packaging Collector Agent ---")
    os.chdir(AGENT_DIR)
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconsole",
        f"--name={APP_NAME}Agent",
        f"--add-data={BACKEND_DIR / '.env'}:.",
        "--add-data=trackflow-context-0.0.1.vsix:.",
        f"--add-data={CHROME_DIR}:chrome-extension",
        "--hidden-import=pymongo",
        "--hidden-import=dns.resolver",
        "--hidden-import=dns.rdatatype",
        # NOTE: For macOS, this requires a collector_mac.py script since collector_windows.py uses ctypes.windll
        "collector_windows.py", 
    ]
    
    # If a generic or mac collector exists, use it instead
    if Path("collector_mac.py").exists():
        cmd[-1] = "collector_mac.py"
        
    subprocess.run(cmd, check=True)
    shutil.copy(Path("dist") / f"{APP_NAME}Agent", DIST_DIR / f"{APP_NAME}Agent")
    (DIST_DIR / f"{APP_NAME}Agent").chmod(0o755)
    os.chdir(ROOT_DIR)


if __name__ == "__main__":
    try:
        clean()
        build_vscode_extension()
        build_frontend()
        build_backend()
        build_agent()
        print(f"\n{'='*60}")
        print(f"SUCCESS! Binaries are in: {DIST_DIR.absolute()}")
        print(f"  - {APP_NAME}Server  (Admin Dashboard + API)")
        print(f"  - {APP_NAME}Agent   (Collector + Extensions)")
        print(f"{'='*60}")
    except Exception as e:
        print(f"\nBUILD FAILED: {e}")
        raise
