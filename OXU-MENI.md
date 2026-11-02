# Şifrələr Kitabçası

Offline, şifrəli parol kitabçası. Master parol olmadan fayl açılmır.

## Fayllar
- `main.py`, `ui.kv` - tətbiq və interfeys
- `vault.py` - şifrələmə (scrypt + AES-256-GCM)
- `clipboard_guard.py` - kopyala + 60 saniyədən sonra sil
- `assets/` - ikon, şrift, interfeys ikonları
- `buildozer.spec` + `.github/workflows/build.yml` - APK qurmaq üçün

## 1) Pydroid 3-də yoxlamaq (APK olmadan)
1. Play Store-dan "Pydroid repository plugin" qur.
2. Pydroid → menyu → Pip → `kivy` və `pycryptodome` qur.
3. Qovluğu telefonda aç, `main.py`-ı işə sal.

## 2) APK qurmaq (Pydroid-də Buildozer işləmir)
Buildozer Linux, Java, Android SDK/NDK tələb edir. Telefonda yox, pulsuz serverdə qur:

**GitHub Actions (tövsiyə):**
1. github.com-da boş repo yarat, bu qovluğun bütün məzmununu (`.github` daxil) yüklə.
2. Actions → "APK qur" → Run workflow. 20-40 dəq. sonra `sifrelerkitabcasi-apk` artefaktını endir.
3. APK-nı telefonda aç ("naməlum mənbədən qurmağa icazə ver").

**Google Colab (alternativ):** qovluğu zip kimi yüklə, aç, sonra:
```
!pip install buildozer "cython<3"
!sudo apt-get install -y openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses5-dev libtinfo5 cmake libffi-dev libssl-dev
!buildozer -v android debug
```

## Qeydlər
- Seyf faylı tətbiqin şəxsi qovluğundadır. Tətbiqi silsən fayl da silinər.
- Master parol unudulsa bərpa yolu yoxdur.
- `main.py`-da `SECURE_SCREEN = True` etsən ekran görüntüsü bloklanır.
