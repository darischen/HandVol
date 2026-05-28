# Windows Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a game-like installer (.exe) that bundles Python, MediaPipe model, and HandVol code, auto-configures Windows Task Scheduler, and requires no user setup.

**Architecture:** NSIS-based installer with bundled Python 3.11 runtime and MediaPipe model. Build script orchestrates fetching/caching embeddable Python, copying MediaPipe model from Git LFS, pre-installing pip packages, and compiling the NSIS script into a standalone .exe. Installer extracts to Program Files, creates Task Scheduler entry, and offers optional auto-launch and desktop shortcut.

**Tech Stack:** NSIS (installer), Git LFS (model storage), Python 3.11 embeddable (bundled runtime), schtasks.exe (Windows API), batch scripts (setup automation).

---

## Task 1: Set up Git LFS for MediaPipe Model

**Files:**
- Modify: `.gitattributes`
- Create: `models/gesture_recognizer.task` (download first)

**Steps:**

- [ ] **Step 1: Check if models/ directory exists**

Run:
```powershell
ls -Force models/ 2>&1
```

If it doesn't exist, create it:
```powershell
mkdir models
```

- [ ] **Step 2: Download MediaPipe model**

Download from: https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task

Save to: `models/gesture_recognizer.task`

Verify file size (~200MB):
```powershell
(Get-Item models/gesture_recognizer.task).Length / 1MB
```

- [ ] **Step 3: Configure Git LFS**

Edit `.gitattributes` (create if doesn't exist) and add:

```
models/gesture_recognizer.task filter=lfs diff=lfs merge=lfs -text
```

- [ ] **Step 4: Initialize Git LFS for the repo**

Run:
```bash
git lfs install
git lfs track models/gesture_recognizer.task
git add .gitattributes models/gesture_recognizer.task
git commit -m "chore: add MediaPipe model via Git LFS"
```

Expected: Git LFS now tracking the model file.

---

## Task 2: Create NSIS Installer Script

**Files:**
- Create: `installer/handvol-installer.nsi`

**Steps:**

- [ ] **Step 1: Create installer directory**

```powershell
mkdir -Force installer
```

- [ ] **Step 2: Write NSIS script**

Create `installer/handvol-installer.nsi`:

```nsis
; HandVol Windows Installer
; Built with NSIS 3.x

!include "MUI2.nsh"
!include "x64.nsh"

; Name and file
Name "HandVol"
OutFile "..\dist\HandVol-Installer.exe"
InstallDir "$PROGRAMFILES\HandVol"
InstallDirRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\HandVol" "InstallLocation"

; Request application privileges for Windows Vista and later
RequestExecutionLevel admin

; MUI Settings
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

; Custom finish page with checkboxes
Page custom FinishPage FinishPageLeave

!insertmacro MUI_LANGUAGE "English"

; Variables for finish page
Var runNow
Var createShortcut

; ============================================================
; Installer Sections
; ============================================================

Section "Install"
  SetOutPath "$INSTDIR"
  
  ; Extract bundled files from build/
  File /r "build\python"
  File /r "build\handvol"
  File /r "build\models"
  File "build\handvol.pyw"
  File "build\requirements.txt"
  File "installer\install_task.bat"
  File "installer\uninstall_task.bat"
  
  ; Create uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; Register in Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\HandVol" "DisplayName" "HandVol"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\HandVol" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\HandVol" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\HandVol" "DisplayVersion" "1.0"
  
  ; Create Task Scheduler entry
  ExecWait '"cmd.exe" /c "$INSTDIR\install_task.bat" "$INSTDIR"'
  
SectionEnd

; ============================================================
; Custom Finish Page
; ============================================================

Function FinishPage
  !insertmacro MUI_HEADER_TEXT "Installation Complete" "Choose what to do next"
  
  ; Create custom page with checkboxes
  nsDialogs::Create 1018
  Pop $0
  
  ${NSD_CreateCheckbox} 0 10 100% 12u "Run HandVol now?"
  Pop $runNow
  ${NSD_SetState} $runNow 1
  
  ${NSD_CreateCheckbox} 0 30 100% 12u "Create desktop shortcut?"
  Pop $createShortcut
  ${NSD_SetState} $createShortcut 1
  
  ${NSD_CreateButton} 0 60 100% 14u "Finish"
  Pop $0
  ${NSD_OnClick} $0 FinishPageButtonClick
  
  nsDialogs::Show
FunctionEnd

Function FinishPageLeave
  ; Handled by button click
FunctionEnd

Function FinishPageButtonClick
  ${NSD_GetState} $runNow $0
  ${NSD_GetState} $createShortcut $1
  
  ; Create desktop shortcut if checked
  ${If} $1 == 1
    CreateDirectory "$DESKTOP"
    CreateShortCut "$DESKTOP\HandVol.lnk" "$INSTDIR\handvol.pyw"
  ${EndIf}
  
  ; Run HandVol if checked
  ${If} $0 == 1
    ExecShell "open" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\handvol.pyw"'
  ${EndIf}
  
  Quit
FunctionEnd

; ============================================================
; Uninstaller
; ============================================================

Section "Uninstall"
  ; Remove Task Scheduler entry
  ExecWait '"cmd.exe" /c "$INSTDIR\uninstall_task.bat"'
  
  ; Remove shortcut if it exists
  Delete "$DESKTOP\HandVol.lnk"
  
  ; Remove registry entries
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\HandVol"
  
  ; Remove all files
  RMDir /r "$INSTDIR"
SectionEnd
```

- [ ] **Step 3: Verify syntax**

NSIS scripts are validated by the compiler. We'll test this in Task 5.

---

## Task 3: Create Task Scheduler Setup Batch Script

**Files:**
- Create: `installer/install_task.bat`

**Steps:**

- [ ] **Step 1: Write install_task.bat**

Create `installer/install_task.bat`:

```batch
@echo off
REM Task Scheduler Setup Script for HandVol
REM Called by NSIS installer with INSTDIR as first argument

setlocal enabledelayedexpansion

REM Get install directory from first argument
set INSTDIR=%1

REM Verify INSTDIR is provided
if "%INSTDIR%"=="" (
    echo Error: INSTDIR not provided
    exit /b 1
)

REM Create Task Scheduler entry
REM /tn: Task name
REM /tr: Task to run (full path to pythonw.exe and script)
REM /sc: Schedule type (onstart = at system startup)
REM /rl: Run level (highest = run with admin privileges)
REM /f: Force creation (overwrite if exists)
REM /np: No password (run with logged-in user's token)

set PYTHONW_PATH="%INSTDIR%\python\pythonw.exe"
set SCRIPT_PATH="%INSTDIR%\handvol.pyw"
set TASK_RUN=!PYTHONW_PATH! !SCRIPT_PATH!

schtasks /create /tn "HandVol" /tr "!TASK_RUN!" /sc onstart /rl highest /f /np

if errorlevel 1 (
    echo Error creating Task Scheduler entry
    exit /b 1
)

echo Task Scheduler entry created successfully
exit /b 0
```

- [ ] **Step 2: Verify the script syntax**

Run locally (won't create actual task without admin):
```batch
installer\install_task.bat "C:\Program Files\HandVol"
```

Expected: Script runs without syntax errors (may fail permission-wise, that's OK for now).

---

## Task 4: Create Task Scheduler Cleanup Batch Script

**Files:**
- Create: `installer/uninstall_task.bat`

**Steps:**

- [ ] **Step 1: Write uninstall_task.bat**

Create `installer/uninstall_task.bat`:

```batch
@echo off
REM Task Scheduler Cleanup Script for HandVol
REM Removes the scheduled task created by install_task.bat

setlocal enabledelayedexpansion

REM Delete the Task Scheduler entry
schtasks /delete /tn "HandVol" /f

if errorlevel 1 (
    echo Error deleting Task Scheduler entry (may not exist)
    exit /b 0
)

echo Task Scheduler entry removed successfully
exit /b 0
```

- [ ] **Step 2: Verify the script**

Run:
```batch
installer\uninstall_task.bat
```

Expected: Script runs, message about task deletion (will fail gracefully if task doesn't exist).

---

## Task 5: Create Build Script

**Files:**
- Create: `build_installer.py`
- Modify: `.gitignore`

**Steps:**

- [ ] **Step 1: Update .gitignore**

Edit `.gitignore` and add:

```
# Installer build artifacts
build/
dist/
*.exe
```

- [ ] **Step 2: Write build_installer.py**

Create `build_installer.py` in repo root:

```python
#!/usr/bin/env python3
"""
Build script for HandVol Windows installer.

Orchestrates:
1. Download/cache embeddable Python 3.11
2. Copy MediaPipe model from Git LFS
3. Copy HandVol source code
4. Install pip packages into bundled Python
5. Compile NSIS script to .exe
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.request import urlopen

PYTHON_VERSION = "3.11.9"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_CACHE = Path("cache/python-embed.zip")
BUILD_DIR = Path("build")
DIST_DIR = Path("dist")
REPO_ROOT = Path(__file__).parent

def log(msg):
    print(f"[BUILD] {msg}", file=sys.stderr)

def download_python():
    """Download embeddable Python 3.11 if not cached."""
    PYTHON_CACHE.parent.mkdir(exist_ok=True)
    
    if PYTHON_CACHE.exists():
        log(f"✓ Python cache found: {PYTHON_CACHE}")
        return
    
    log(f"Downloading Python {PYTHON_VERSION}...")
    try:
        with urlopen(PYTHON_URL) as response:
            with open(PYTHON_CACHE, "wb") as f:
                f.write(response.read())
        log(f"✓ Downloaded to {PYTHON_CACHE}")
    except Exception as e:
        log(f"✗ Failed to download Python: {e}")
        sys.exit(1)

def extract_python():
    """Extract embeddable Python to build/python/"""
    python_dir = BUILD_DIR / "python"
    
    if python_dir.exists():
        log(f"✓ Python already extracted to {python_dir}")
        return
    
    log(f"Extracting Python to {python_dir}...")
    with zipfile.ZipFile(PYTHON_CACHE, "r") as z:
        z.extractall(python_dir)
    log(f"✓ Extracted {PYTHON_CACHE}")

def copy_mediapipe_model():
    """Copy MediaPipe model from repo (via Git LFS)."""
    src = REPO_ROOT / "models" / "gesture_recognizer.task"
    dst = BUILD_DIR / "models" / "gesture_recognizer.task"
    
    if not src.exists():
        log(f"✗ MediaPipe model not found at {src}")
        log("  Run: git lfs pull")
        sys.exit(1)
    
    dst.parent.mkdir(parents=True, exist_ok=True)
    
    if dst.exists():
        log(f"✓ MediaPipe model already copied to {dst}")
        return
    
    log(f"Copying MediaPipe model to {dst}...")
    shutil.copy2(src, dst)
    log(f"✓ Copied {src.stat().st_size / (1024**2):.1f} MB")

def install_pip_packages():
    """Install pip packages into bundled Python."""
    python_exe = BUILD_DIR / "python" / "python.exe"
    requirements = REPO_ROOT / "requirements.txt"
    
    if not python_exe.exists():
        log(f"✗ Python executable not found at {python_exe}")
        sys.exit(1)
    
    log("Installing pip packages...")
    result = subprocess.run(
        [str(python_exe), "-m", "pip", "install", "-r", str(requirements),
         "-t", str(BUILD_DIR / "python" / "Lib" / "site-packages")],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        log(f"✗ pip install failed: {result.stderr}")
        sys.exit(1)
    
    log("✓ Installed all packages")

def copy_handvol_source():
    """Copy HandVol source code to build/"""
    src = REPO_ROOT / "handvol"
    dst = BUILD_DIR / "handvol"
    
    if dst.exists():
        shutil.rmtree(dst)
    
    log(f"Copying HandVol source to {dst}...")
    shutil.copytree(src, dst)
    
    # Copy main script
    shutil.copy2(REPO_ROOT / "handvol.pyw", BUILD_DIR / "handvol.pyw")
    shutil.copy2(REPO_ROOT / "requirements.txt", BUILD_DIR / "requirements.txt")
    
    log(f"✓ Copied source code")

def compile_nsis():
    """Compile NSIS script to .exe"""
    nsis_script = REPO_ROOT / "installer" / "handvol-installer.nsi"
    
    if not nsis_script.exists():
        log(f"✗ NSIS script not found at {nsis_script}")
        sys.exit(1)
    
    # Check if makensis.exe is available
    try:
        subprocess.run(["makensis", "-VERSION"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log("✗ NSIS not installed or not in PATH")
        log("  Download: https://nsis.sourceforge.io/Download")
        sys.exit(1)
    
    DIST_DIR.mkdir(exist_ok=True)
    
    log("Compiling NSIS script...")
    result = subprocess.run(
        ["makensis", str(nsis_script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT)
    )
    
    if result.returncode != 0:
        log(f"✗ NSIS compilation failed: {result.stderr}")
        sys.exit(1)
    
    exe_path = DIST_DIR / "HandVol-Installer.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024**2)
        log(f"✓ Built {exe_path} ({size_mb:.1f} MB)")
    else:
        log(f"✗ Installer .exe not found at {exe_path}")
        sys.exit(1)

def main():
    log("HandVol Windows Installer Builder")
    log("=" * 50)
    
    # Ensure we're in the repo root
    if not (REPO_ROOT / "handvol.pyw").exists():
        log(f"✗ Not in HandVol repo root")
        sys.exit(1)
    
    # Clean build directory
    if BUILD_DIR.exists():
        log(f"Cleaning {BUILD_DIR}...")
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(exist_ok=True)
    
    # Execute build steps
    download_python()
    extract_python()
    copy_mediapipe_model()
    copy_handvol_source()
    install_pip_packages()
    compile_nsis()
    
    log("=" * 50)
    log(f"✓ Build complete! Installer: {DIST_DIR / 'HandVol-Installer.exe'}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify build script**

Run:
```powershell
python build_installer.py
```

Expected output:
```
[BUILD] HandVol Windows Installer Builder
[BUILD] ==================================================
[BUILD] Downloading Python 3.11.9...
[BUILD] ✓ Downloaded to cache/python-embed.zip
[BUILD] Extracting Python to build\python...
[BUILD] ✓ Extracted
...
[BUILD] ✓ Build complete! Installer: dist\HandVol-Installer.exe
```

This will take a few minutes on first run due to Python download and pip install.

- [ ] **Step 4: Commit the build script**

```bash
git add build_installer.py installer/ .gitignore
git commit -m "feat: add NSIS installer and build script"
```

---

## Task 6: Create Installer Documentation

**Files:**
- Create: `installer/README.md`

**Steps:**

- [ ] **Step 1: Write installer README**

Create `installer/README.md`:

```markdown
# HandVol Windows Installer

This directory contains the files needed to build the `HandVol-Installer.exe`.

## Prerequisites

- Windows 10/11
- Python 3.11+
- NSIS 3.x (download from https://nsis.sourceforge.io/Download)
- Git with Git LFS (`git lfs install`)

## Building the Installer

From the repo root, run:

```powershell
python build_installer.py
```

This script will:
1. Download embeddable Python 3.11 (cached after first run)
2. Copy MediaPipe model from `models/gesture_recognizer.task` (requires `git lfs pull`)
3. Copy HandVol source code
4. Install all pip dependencies
5. Compile the NSIS script to `dist/HandVol-Installer.exe`

Expected output: `dist/HandVol-Installer.exe` (~300-400MB)

## Files

- `handvol-installer.nsi` — NSIS installer script with wizard UI
- `install_task.bat` — Creates Windows Task Scheduler entry (called by installer)
- `uninstall_task.bat` — Removes Task Scheduler entry (called by uninstaller)

## Testing

### On Fresh Windows VM

1. Copy `dist/HandVol-Installer.exe` to the VM
2. Run the installer (requires admin)
3. Verify:
   - Wizard appears with install path, checkboxes
   - Files extracted to `C:\Program Files\HandVol\`
   - Task Scheduler entry `HandVol` created
   - Optional: Launch and shortcut work
   - Task runs automatically at next boot

### Uninstall Test

1. Open Add/Remove Programs
2. Find "HandVol" and click Uninstall
3. Verify:
   - `C:\Program Files\HandVol\` deleted
   - Task Scheduler entry `HandVol` removed
   - Desktop shortcut (if created) removed
   - Registry entries cleaned

## Troubleshooting

**"NSIS not installed or not in PATH"**
- Download and install NSIS from https://nsis.sourceforge.io/Download
- Ensure `makensis.exe` is in PATH

**"MediaPipe model not found"**
- Run: `git lfs pull`
- Verify `models/gesture_recognizer.task` exists and is ~200MB

**"Python download failed"**
- Check internet connection
- Delete `cache/python-embed.zip` and retry
```

- [ ] **Step 2: Commit**

```bash
git add installer/README.md
git commit -m "docs: add installer build and testing guide"
```

---

## Task 7: Test Build Script on Development Machine

**Files:**
- No new files (testing existing build script)

**Steps:**

- [ ] **Step 1: Verify NSIS is installed**

Run:
```bash
makensis -VERSION
```

Expected: Version info printed (e.g., "v3.08")

If not found, download from https://nsis.sourceforge.io/Download and add to PATH.

- [ ] **Step 2: Ensure Git LFS is set up**

Run:
```bash
git lfs ls-files
```

Expected: `models/gesture_recognizer.task` listed and file exists locally.

If not, run:
```bash
git lfs pull
```

- [ ] **Step 3: Run build script (partial test)**

On Windows, run:
```powershell
python build_installer.py
```

Expected:
- Python downloads and extracts
- MediaPipe model copied
- HandVol source copied
- pip packages installed
- NSIS compilation succeeds
- `dist/HandVol-Installer.exe` created (~300-400MB)

This may take 5-10 minutes.

- [ ] **Step 4: Verify installer file**

```powershell
ls -lh dist/HandVol-Installer.exe
```

Expected: File exists and is ~300-400MB.

- [ ] **Step 5: Commit and note success**

```bash
git add -A
git commit -m "test: verify build script creates installer successfully"
```

---

## Task 8: Manual Test on Fresh Windows VM (if available)

**Files:**
- No new files (manual testing)

**Steps:**

- [ ] **Step 1: Prepare fresh Windows VM**

If you have access to a fresh Windows 10/11 VM:
- Copy `dist/HandVol-Installer.exe` to the VM
- Ensure user account has admin rights

- [ ] **Step 2: Run installer**

Double-click `HandVol-Installer.exe`

Expected: NSIS wizard appears with welcome screen

- [ ] **Step 3: Test wizard flow**

1. Click "Next" on welcome
2. Choose install path (accept default)
3. Click "Next"
4. Verify "Ready to Install" screen shows correct path
5. Click "Install"
6. Verify extraction progress bar appears and completes
7. Verify finish screen with checkboxes appears

- [ ] **Step 4: Test finish options**

On finish screen:
- Check "Run HandVol now?"
- Check "Create desktop shortcut?"
- Click "Finish"

Expected:
- Installer closes
- `C:\Program Files\HandVol\` directory created with all files
- Desktop shortcut appears
- HandVol app launches (system tray icon visible)

- [ ] **Step 5: Verify Task Scheduler entry**

Open Task Scheduler (search "Task Scheduler"):
- Navigate to Task Scheduler Library
- Look for task named "HandVol"
- Verify: Trigger = "At startup", Action = "Run pythonw.exe..."

- [ ] **Step 6: Test uninstall**

Open Add/Remove Programs (Settings > Apps > Installed apps):
- Search for "HandVol"
- Click "Uninstall"
- Verify uninstall completes
- Verify `C:\Program Files\HandVol\` deleted
- Verify Task Scheduler entry removed
- Verify desktop shortcut removed

- [ ] **Step 7: Document results**

If testing is successful, add a note to `installer/README.md`:

```markdown
## Testing Results

- [x] Fresh Windows 10/11 install successful
- [x] Wizard UI works correctly
- [x] Task Scheduler entry created
- [x] Desktop shortcut creation works
- [x] App launches correctly after install
- [x] Uninstall removes all files and entries
```

Then commit:
```bash
git add installer/README.md
git commit -m "test: verify installer on fresh Windows VM"
```

---

## Checklist Summary

- [ ] Task 1: Git LFS setup for MediaPipe model
- [ ] Task 2: NSIS installer script written
- [ ] Task 3: Task Scheduler setup batch script
- [ ] Task 4: Task Scheduler cleanup batch script
- [ ] Task 5: Build script completed and verified
- [ ] Task 6: Installer documentation written
- [ ] Task 7: Build script tested on dev machine
- [ ] Task 8: (Optional) Manual test on fresh Windows VM
