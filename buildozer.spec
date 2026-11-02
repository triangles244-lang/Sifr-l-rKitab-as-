[app]
title = Şifrələr Kitabçası
package.name = sifrelerkitabcasi
package.domain = az.sifrelerkitabcasi

source.dir = .
source.include_exts = py,kv,png,ttf
source.exclude_dirs = .github,bin,.buildozer,__pycache__
version = 1.0

# pycryptodome: Android-də qurulması cryptography-dən daha etibarlıdır.
# vault.py hər ikisini dəstəkləyir, fayllar eynidir.
requirements = python3,kivy==2.3.0,pycryptodome,pyjnius,android

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/icon.png
android.presplash_color = #05080F

orientation = portrait
fullscreen = 0

# İnternet və yaddaş icazələri lazım deyil: tam offline.
android.permissions =
android.allow_backup = False

android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1
