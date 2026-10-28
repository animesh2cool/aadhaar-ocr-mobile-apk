# How to Build the Android APK using Buildozer

This project contains the complete offline Kivy application and `buildozer.spec`.

---

## 1. Test the App Natively on Your Laptop
You can launch the native mobile window directly on your laptop screen right now:
```bash
python main.py
```
This opens the mobile application in a 400x800 smartphone aspect ratio window with camera picker, offline OCR extraction, and 1-tap offline Excel export.

---

## 2. Compile into an Android `.apk` File

> **Note:** Buildozer requires a Linux build environment to package Android bytecodes and libraries. Since you are on Windows, choose any of the 3 simple methods below:

### Method A: Free 1-Click Google Colab (Fastest — No Linux needed)
1. Open a new notebook on [Google Colab](https://colab.research.google.com/).
2. Run these commands:
```python
# 1. Install Buildozer dependencies
!sudo apt update
!sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
!pip install --upgrade cython buildozer

# 2. Upload main.py, aadhaar_ocr.py, and buildozer.spec from test-folder

# 3. Build the APK
!buildozer -v android debug

# 4. Download your APK
from google.colab import files
import glob
apk_files = glob.glob('bin/*.apk')
if apk_files:
    files.download(apk_files[0])
```
3. Your compiled `.apk` will automatically download to your phone or laptop!

---

### Method B: GitHub Actions (Automated Cloud Build)
The workflow file is already added in [`.github/workflows/build_apk.yml`](.github/workflows/build_apk.yml).
1. Push this folder to a GitHub repository.
2. Go to the **Actions** tab on your GitHub repository.
3. Click **"Run workflow"** on **Build Android APK with Buildozer**.
4. When finished, download the ready-to-install `.apk` artifact directly from GitHub!

---

### Method C: Local WSL2 (Ubuntu on Windows)
If you have WSL installed:
```bash
wsl
cd /mnt/c/Users/debas/Videos/Big-Five/test-folder
sudo apt update && sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses-dev libtinfo6 cmake libffi-dev libssl-dev
pip install --upgrade cython buildozer
buildozer android debug
```
The APK will appear in `bin/aadhaarscan-1.0.0-arm64-v8a-debug.apk`.


Success