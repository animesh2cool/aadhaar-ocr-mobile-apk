[app]

# ---- App identity ----------------------------------------------------------
title = AadhaarScan
package.name = aadhaarscan
package.domain = org.kalim.aadhaar
version = 1.0.0

# ---- Source ----------------------------------------------------------------
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
source.exclude_dirs = tests,bin,venv,.git,.github,.buildozer
source.exclude_patterns = test_*.py,smoke.py

# ---- Python requirements ---------------------------------------------------
# Only pure-Python packages or ones that have a python-for-android recipe.
# Do NOT add packages with compiled code (charset-normalizer, numpy, openpyxl's
# optional C extras, etc.) unless a recipe exists - that is what broke the build.
requirements = python3,kivy,pyjnius,android,pillow,xlsxwriter,androidstorage4kivy

# ---- python-for-android ----------------------------------------------------
# Pinned so the toolchain (and its Python version) can't change under you.
# Unpinned "master" had moved to Python 3.14, which broke the pip install step.
p4a.branch = v2024.01.21
p4a.bootstrap = sdl2
# Only enable if ./p4a_recipes contains recipes you actually need
# (e.g. a custom pillow recipe). Not needed for the requirements above.
# p4a.local_recipes = ./p4a_recipes

# ---- Display ---------------------------------------------------------------
orientation = portrait
fullscreen = 0

# ---- Android ---------------------------------------------------------------
# Gallery picking and saving to Downloads use the system file picker /
# MediaStore, so no storage permissions are needed.
android.permissions = CAMERA

android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a

# AndroidX is required by Google ML Kit and androidstorage4kivy
android.enable_androidx = True
android.gradle_dependencies = com.google.mlkit:text-recognition:16.0.0, com.google.mlkit:vision-common:17.3.0, com.google.android.gms:play-services-tasks:18.1.0, androidx.documentfile:documentfile:1.0.1

# Keep card data out of Android cloud/adb backups
android.allow_backup = False

android.accept_sdk_license = True
android.skip_update = False
android.release_artifact = apk
android.debug_artifact = apk

# Readable runtime logs: adb logcat (Python output only)
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
