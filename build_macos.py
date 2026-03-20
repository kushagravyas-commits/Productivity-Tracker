import os
import shutil
import subprocess
from pathlib import Path

# Configuration
APP_NAME = "TrackFlow"
ROOT_DIR = Path(__file__).parent.resolve()
DIST_DIR = ROOT_DIR / "electron-mac" / "bin"
FRONTEND_DIR = ROOT_DIR / "frontend"
BACKEND_DIR = ROOT_DIR / "backend"
AGENT_DIR = ROOT_DIR / "agent"
VSCODE_DIR = ROOT_DIR / "vscode-extension"
CHROME_DIR = ROOT_DIR / "chrome-extension"

def clean():
    print("Cleaning old builds...")
    for d in [BACKEND_DIR / "build", BACKEND_DIR / "dist",
              AGENT_DIR / "build", AGENT_DIR / "dist", BACKEND_DIR / "static"]:
        if d.exists():
            shutil.rmtree(d)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

def build_frontend():
    print("\n--- Building Frontend ---")
    os.chdir(FRONTEND_DIR)
    if not (FRONTEND_DIR / "node_modules").exists():
        print("Installing Frontend dependencies...")
        subprocess.run("npm install", shell=True, check=True)
        
    if os.name != "nt":
        # Ensure vite and other binaries are executable
        bin_path = FRONTEND_DIR / "node_modules" / ".bin"
        if bin_path.exists():
            subprocess.run(f"chmod +x {bin_path}/*", shell=True, check=True)

    subprocess.run("npm run build", shell=True, check=True)
    static_dest = BACKEND_DIR / "static"
    if static_dest.exists():
        shutil.rmtree(static_dest)
    shutil.copytree(FRONTEND_DIR / "dist", static_dest)
    os.chdir(ROOT_DIR)

def build_vscode_extension():
    print("\n--- Building VS Code Extension ---")
    os.chdir(VSCODE_DIR)
    if not (VSCODE_DIR / "node_modules").exists():
        print("Installing VS Code extension dependencies...")
        subprocess.run("npm install", shell=True, check=True)

    if os.name != "nt":
        # On Mac/Linux, ensure vsce has execute permissions
        vsce_path = VSCODE_DIR / "node_modules" / ".bin" / "vsce"
        if vsce_path.exists():
            subprocess.run(["chmod", "+x", str(vsce_path)], check=True)
            
    subprocess.run("npm run package", shell=True, check=True)
    vsix = VSCODE_DIR / "trackflow-context-0.0.1.vsix"
    shutil.copy(vsix, AGENT_DIR / "trackflow-context-0.0.1.vsix")
    os.chdir(ROOT_DIR)

def build_backend():
    print("\n--- Packaging Backend (Admin Dashboard) ---")
    os.chdir(BACKEND_DIR)
    
    # Use : for separator on macOS/Linux, ; on Windows
    sep = ";" if os.name == "nt" else ":"
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--windowed", # Equivalent to --noconsole
        f"--name={APP_NAME}Server",
        f"--add-data=static{sep}static",
        f"--add-data=.env{sep}.",
        "--hidden-import=motor",
        "--hidden-import=motor.motor_asyncio",
        "--hidden-import=uvicorn",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=dns.resolver",
        "app/main.py",
    ]
    
    if os.name == "nt":
        print("\n[WARNING] You are running this on WINDOWS. This script will only produced Windows (.exe) binaries.")
        print("          To build a real macOS (.app) bundle, you MUST run this on a Mac.")

    subprocess.run(cmd, check=True)
    
    # Detect extension based on current OS (for testing on Windows)
    ext = ".exe" if os.name == "nt" else ""
    src = Path("dist") / f"{APP_NAME}Server{ext}"
    dest = DIST_DIR / f"{APP_NAME}Server{ext}"
    
    if not src.exists():
        raise FileNotFoundError(f"Could not find build output at {src}. PyInstaller might have failed.")
        
    shutil.copy(src, dest)
    os.chdir(ROOT_DIR)

def build_agent():
    print("\n--- Packaging Collector Agent ---")
    os.chdir(AGENT_DIR)
    
    sep = ";" if os.name == "nt" else ":"
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--windowed",
        f"--name={APP_NAME}Agent",
        f"--add-data={BACKEND_DIR / '.env'}{sep}.",
        f"--add-data=trackflow-context-0.0.1.vsix{sep}.",
        f"--add-data={CHROME_DIR}{sep}chrome-extension",
        "--hidden-import=pymongo",
        "--hidden-import=dns.resolver",
        "collector_macos.py",
    ]
    
    subprocess.run(cmd, check=True)
    
    ext = ".exe" if os.name == "nt" else ""
    src = Path("dist") / f"{APP_NAME}Agent{ext}"
    dest = DIST_DIR / f"{APP_NAME}Agent{ext}"
    
    if not src.exists():
        raise FileNotFoundError(f"Could not find build output at {src}. PyInstaller might have failed.")
        
    shutil.copy(src, dest)
    os.chdir(ROOT_DIR)

if __name__ == "__main__":
    try:
        clean()
        build_vscode_extension()
        build_frontend()
        build_backend()
        # Only build agent if the mac entry point exists
        if (AGENT_DIR / "collector_macos.py").exists():
            build_agent()
        print(f"\nSUCCESS! Binaries in: {DIST_DIR}")
    except Exception as e:
        print(f"\nBUILD FAILED: {e}")
        raise
