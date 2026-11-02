"""Kopyalama + 60 saniyədən sonra buferi təmizləmə.

* Android-də pyjnius ilə "həssas" bayrağı qoyulur (Android 13+ önizləmədə göstərmir).
* Təmizləmə threading.Timer ilə edilir ki, tətbiq arxa fonda olanda da işləsin.
* Tətbiq geri qayıdanda (on_resume) vaxt keçibsə, yenə yoxlanılır.
* Pydroid / kompüterdə jnius yoxdursa, Kivy-nin öz clipboard-ına keçir.
"""
import threading
import time

from kivy.clock import mainthread
from kivy.core.clipboard import Clipboard

CLEAR_AFTER = 60  # saniyə

try:
    from android.runnable import run_on_ui_thread
except Exception:  # Android deyil
    def run_on_ui_thread(func):
        return func

_lock = threading.Lock()
_timer = None
_deadline = 0.0
_last = None  # axırıncı kopyalanan mətn (yalnız bizimki silinsin deyə)


# ---------------------------------------------------------------- Android
def _android_ctx():
    from jnius import autoclass
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    context = autoclass("android.content.Context")
    return activity, activity.getSystemService(context.CLIPBOARD_SERVICE)


@run_on_ui_thread
def _android_set(text, sensitive):
    from jnius import autoclass
    _, cm = _android_ctx()
    clip = autoclass("android.content.ClipData").newPlainText("Şifrələr Kitabçası", text)
    if sensitive:
        try:
            bundle = autoclass("android.os.PersistableBundle")()
            bundle.putBoolean("android.content.extra.IS_SENSITIVE", True)
            clip.getDescription().setExtras(bundle)
        except Exception:
            pass
    cm.setPrimaryClip(clip)


@run_on_ui_thread
def _android_clear():
    from jnius import autoclass
    _, cm = _android_ctx()
    try:
        cm.clearPrimaryClip()          # Android 9+
    except Exception:
        cm.setPrimaryClip(autoclass("android.content.ClipData").newPlainText("", ""))


def _android_read():
    """Cari mətni qaytarır. Android 10+ arxa fonda oxumağa icazə vermir -> None."""
    try:
        activity, cm = _android_ctx()
        clip = cm.getPrimaryClip()
        if clip is None or clip.getItemCount() == 0:
            return None
        return clip.getItemAt(0).coerceToText(activity).toString()
    except Exception:
        return None


# ------------------------------------------------------------------ ortaq
_ANDROID = None


def _android_ok():
    global _ANDROID
    if _ANDROID is None:
        try:
            from jnius import autoclass
            autoclass("org.kivy.android.PythonActivity").mActivity  # noqa: B018
            _ANDROID = True
        except Exception:
            _ANDROID = False
    return _ANDROID


@mainthread
def _kivy_set(text):
    try:
        Clipboard.copy(text)
    except Exception:
        pass


def copy_secret(text):
    """Mətni buferə qoyur və CLEAR_AFTER saniyə sonra təmizləməni planlaşdırır."""
    global _timer, _deadline, _last
    if _android_ok():
        try:
            _android_set(text, True)
        except Exception:
            _kivy_set(text)
    else:
        _kivy_set(text)

    with _lock:
        if _timer is not None:
            _timer.cancel()
        _last = text
        _deadline = time.time() + CLEAR_AFTER
        _timer = threading.Timer(CLEAR_AFTER, _clear_now)
        _timer.daemon = True
        _timer.start()


def _clear_now():
    global _timer, _deadline, _last
    with _lock:
        if _last is None:
            return
        mine = _last
        _last = None
        _deadline = 0.0
        _timer = None
    if _android_ok():
        current = _android_read()
        # oxuna bilmirsə (arxa fon) və ya hələ bizim mətndirsə -> sil
        if current is None or current == "" or current == mine:
            try:
                _android_clear()
            except Exception:
                pass
    else:
        _kivy_set("")


def check_expired():
    """on_resume zamanı çağırılır: vaxt çoxdan keçibsə, dərhal təmizlə."""
    with _lock:
        due = _last is not None and _deadline and time.time() >= _deadline
    if due:
        _clear_now()


def clear_now():
    """Seyf kilidlənəndə dərhal təmizləmək üçün."""
    with _lock:
        if _timer is not None:
            _timer.cancel()
    _clear_now()
