"""Şifrələr Kitabçası - offline, şifrəli parol kitabçası (Kivy)."""
import os
import threading
import time

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import mainthread
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import (BooleanProperty, ColorProperty, NumericProperty,
                             StringProperty)
from kivy.resources import resource_add_path
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.widget import Widget

import clipboard_guard
from vault import Vault, VaultError, WrongPassword, generate_password

BASE = os.path.dirname(os.path.abspath(__file__))
resource_add_path(BASE)

# Carlito şrifti: ə, ş, ç, ğ, ı, İ, ö, ü hərflərinin hamısını dəstəkləyir.
LabelBase.register(
    name="Roboto",
    fn_regular=os.path.join(BASE, "assets", "fonts", "Carlito-Regular.ttf"),
    fn_bold=os.path.join(BASE, "assets", "fonts", "Carlito-Bold.ttf"),
)

ICONS = "assets/icons/"
AUTO_LOCK_SECONDS = 300      # arxa fonda 5 dəqiqədən çox qalsa kilidlə
SECURE_SCREEN = False        # True: ekran görüntüsünü və "son tətbiqlər" önizləməsini bloklayır

CATS = {
    "web": dict(title="Veb hesabları", sub="Sayt və xidmət qeydləri", icon="globe",
                bg="#2B3A5C", fg="#9DB8FF"),
    "game": dict(title="Oyun hesabları", sub="Oyun profilləri və qeydlər", icon="gamepad",
                 bg="#4A3A28", fg="#FFC27A"),
    "mail": dict(title="E-poçt hesabları", sub="Şəxsi hesab qeydləri", icon="mail",
                 bg="#3B2A52", fg="#D5B0FF"),
}


# ============================================================ kiçik köməkçilər
def run_bg(func, done):
    """func-u fonda işlədir (scrypt ~1 san.), done(result, error)-u əsas axında çağırır."""
    @mainthread
    def finish(result, error):
        done(result, error)

    def worker():
        try:
            result, error = func(), None
        except Exception as exc:  # noqa: BLE001
            result, error = None, exc
        finish(result, error)

    threading.Thread(target=worker, daemon=True).start()


# ================================================================== vidjetlər
class HLabel(Label):
    pass


class TLabel(Label):
    pass


class Icon(Image):
    pass


class Divider(Widget):
    pass


class Card(BoxLayout):
    bg = ColorProperty([0, 0, 0, 0])
    border = ColorProperty([0, 0, 0, 0])
    radius = NumericProperty(dp(22))


class TapCard(ButtonBehavior, Card):
    pass


class IconTile(Card):
    icon = StringProperty("")
    fg = ColorProperty([1, 1, 1, 1])
    isize = NumericProperty(dp(28))


class IconButton(ButtonBehavior, FloatLayout):
    icon = StringProperty("")
    tint = ColorProperty([1, 1, 1, 1])
    bg = ColorProperty([0, 0, 0, 0])
    isize = NumericProperty(dp(24))


class PillButton(TapCard):
    text = StringProperty("")
    icon = StringProperty("")
    fg = ColorProperty([1, 1, 1, 1])
    fsize = NumericProperty(dp(18))
    isize = NumericProperty(dp(22))


class CategoryRow(TapCard):
    title = StringProperty("")
    subtitle = StringProperty("")
    icon = StringProperty("")
    tile_bg = ColorProperty([0.2, 0.2, 0.2, 1])
    tile_fg = ColorProperty([1, 1, 1, 1])
    count = NumericProperty(0)


class InputCard(Card):
    text = StringProperty("")
    hint_text = StringProperty("")
    password = BooleanProperty(False)
    secret_toggle = BooleanProperty(False)


class Chip(TapCard):
    text = StringProperty("")
    selected = BooleanProperty(False)


class FieldRow(BoxLayout):
    caption = StringProperty("")
    value = StringProperty("")
    secret = BooleanProperty(False)
    revealed = BooleanProperty(False)
    __events__ = ("on_copy",)

    def on_copy(self):
        pass


class EntryCard(Card):
    title = StringProperty("")
    username = StringProperty("")
    password = StringProperty("")
    __events__ = ("on_edit", "on_copy_user", "on_copy_pw")

    def on_edit(self):
        pass

    def on_copy_user(self):
        pass

    def on_copy_pw(self):
        pass


class ConfirmCard(Card):
    title = StringProperty("")
    message = StringProperty("")
    ok_text = StringProperty("Sil")
    __events__ = ("on_ok", "on_cancel")

    def on_ok(self):
        pass

    def on_cancel(self):
        pass


class Toast(Card):
    text = StringProperty("")

    # Görünməzkən toxunuşları bloklamasın
    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False


# =================================================================== ekranlar
class LockScreen(Screen):
    creating = BooleanProperty(False)
    busy = BooleanProperty(False)
    message = StringProperty("")
    msg_color = ColorProperty([1, 0.54, 0.5, 1])

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        self.creating = not Vault.exists(app.vault_path)
        self.reset()

    def reset(self):
        self.busy = False
        self.message = ""
        for name in ("master", "confirm"):
            self.ids[name].text = ""
            self.ids[name].password = True

    def submit(self):
        if self.busy:
            return
        app = App.get_running_app()
        pw = self.ids.master.text
        if self.creating:
            if len(pw) < 8:
                self.message = "Master parol ən azı 8 simvol olsun."
                return
            if pw != self.ids.confirm.text:
                self.message = "Parollar eyni deyil."
                return
        elif not pw:
            return

        self.busy = True
        self.message = "İşlənir… bir neçə saniyə çəkə bilər."
        self.msg_color = app.muted
        path, creating = app.vault_path, self.creating

        def work():
            return Vault.create(path, pw) if creating else Vault.open(path, pw)

        def done(vault, error):
            self.busy = False
            if error is not None:
                self.msg_color = app.danger
                if isinstance(error, WrongPassword):
                    self.message = "Master parol səhvdir."
                elif isinstance(error, VaultError):
                    self.message = str(error)
                else:
                    self.message = "Xəta: %s" % error
                return
            self.reset()
            app.unlocked(vault)

        run_bg(work, done)


class HomeScreen(Screen):
    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.rows = {}
        box = self.ids.cat_box
        for i, key in enumerate(CATS):
            meta = CATS[key]
            if i:
                box.add_widget(Divider())
            row = CategoryRow(title=meta["title"], subtitle=meta["sub"],
                              icon=ICONS + meta["icon"] + ".png",
                              tile_bg=meta["bg"], tile_fg=meta["fg"])
            row.bind(on_release=lambda w, k=key: App.get_running_app().open_category(k))
            box.add_widget(row)
            self.rows[key] = row

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        for key, row in self.rows.items():
            row.count = app.vault.count(key) if app.vault else 0
        app.refresh_count()


class CategoryScreen(Screen):
    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):
        app = App.get_running_app()
        meta = CATS[app.cat]
        self.ids.title.text = meta["title"]
        tile = self.ids.tile
        tile.icon = ICONS + meta["icon"] + ".png"
        tile.bg = meta["bg"]
        tile.fg = meta["fg"]

        box = self.ids.list
        box.clear_widgets()
        items = app.vault.entries(app.cat) if app.vault else []
        self.ids.empty.opacity = 0 if items else 1
        for e in items:
            card = EntryCard(title=e["title"], username=e["user"], password=e["pw"])
            eid = e["id"]
            card.bind(
                on_edit=lambda w, i=eid: app.edit_entry(i),
                on_copy_user=lambda w, i=eid: app.copy_field(i, "user", "İstifadəçi adı"),
                on_copy_pw=lambda w, i=eid: app.copy_field(i, "pw", "Parol"),
            )
            box.add_widget(card)

    def wipe(self):
        self.ids.list.clear_widgets()


class EditScreen(Screen):
    cat = StringProperty("web")
    editing_id = StringProperty("")
    message = StringProperty("")
    back = StringProperty("home")

    def load(self, entry_id, cat, back):
        app = App.get_running_app()
        self.back = back
        self.message = ""
        self.editing_id = entry_id or ""
        e = app.vault.get(entry_id) if entry_id else None
        if e:
            self.ids.title_in.text = e["title"]
            self.ids.user_in.text = e["user"]
            self.ids.pw_in.text = e["pw"]
            self.set_cat(e["cat"])
        else:
            self.ids.title_in.text = ""
            self.ids.user_in.text = ""
            self.ids.pw_in.text = ""
            self.set_cat(cat or "web")
        self.ids.pw_in.password = True

    def wipe(self):
        for name in ("title_in", "user_in", "pw_in"):
            self.ids[name].text = ""
        self.editing_id = ""

    def set_cat(self, cat):
        self.cat = cat
        for key in CATS:
            self.ids["chip_" + key].selected = key == cat

    def generate(self):
        self.ids.pw_in.text = generate_password()
        self.ids.pw_in.password = False

    def save(self):
        app = App.get_running_app()
        title = self.ids.title_in.text.strip()
        user = self.ids.user_in.text.strip()
        pw = self.ids.pw_in.text
        if not title:
            self.message = "Ad boş ola bilməz."
            return
        if not pw:
            self.message = "Parol boş ola bilməz."
            return
        try:
            if self.editing_id:
                app.vault.update(self.editing_id, cat=self.cat, title=title, user=user, pw=pw)
            else:
                app.vault.add(self.cat, title, user, pw)
        except (VaultError, OSError) as exc:
            self.message = "Saxlanmadı: %s" % exc
            return
        app.toast("Yadda saxlanıldı")
        app.cat = self.cat
        self.wipe()
        app.go("category", "right")

    def ask_delete(self):
        app = App.get_running_app()
        eid = self.editing_id
        if not eid:
            return

        def do_delete():
            app.vault.delete(eid)
            app.toast("Qeyd silindi")
            self.wipe()
            app.go("category", "right")

        app.confirm("Qeydi sil?", "Bu qeyd həmişəlik silinəcək.", "Sil", do_delete)


class SettingsScreen(Screen):
    pass


class ChangePwScreen(Screen):
    busy = BooleanProperty(False)
    message = StringProperty("")
    msg_color = ColorProperty([1, 0.54, 0.5, 1])

    def on_pre_enter(self, *args):
        self.busy = False
        self.message = ""
        for name in ("old_in", "new_in", "new2_in"):
            self.ids[name].text = ""
            self.ids[name].password = True

    def submit(self):
        if self.busy:
            return
        app = App.get_running_app()
        old, new, new2 = (self.ids.old_in.text, self.ids.new_in.text, self.ids.new2_in.text)
        self.msg_color = app.danger
        if not old:
            self.message = "Cari master parolu yaz."
            return
        if len(new) < 8:
            self.message = "Yeni parol ən azı 8 simvol olsun."
            return
        if new != new2:
            self.message = "Yeni parollar eyni deyil."
            return

        self.busy = True
        self.msg_color = app.muted
        self.message = "İşlənir… bir neçə saniyə çəkə bilər."
        vault = app.vault

        def work():
            if not vault.check_password(old):
                raise WrongPassword("Cari master parol səhvdir.")
            vault.change_password(new)

        def done(_result, error):
            self.busy = False
            if error is not None:
                self.msg_color = app.danger
                self.message = str(error) if isinstance(error, VaultError) else "Xəta: %s" % error
                return
            for name in ("old_in", "new_in", "new2_in"):
                self.ids[name].text = ""
            app.toast("Master parol dəyişdi")
            app.go("settings", "right")

        run_bg(work, done)


# ====================================================================== tətbiq
class SifrelerKitabcasiApp(App):
    accent = ColorProperty("#6EE7A0")
    on_accent = ColorProperty("#0B1F15")
    card = ColorProperty("#1B2420")
    card2 = ColorProperty("#26332D")
    border = ColorProperty("#2E3D36")
    muted = ColorProperty("#9AA8A2")
    danger = ColorProperty("#FF8A80")
    danger_bg = ColorProperty("#3A2222")

    entry_count = NumericProperty(0)
    cat = StringProperty("web")
    vault_path = StringProperty("")
    vault = None

    # ---- qurulum
    def build(self):
        self.title = "Şifrələr Kitabçası"
        self.icon = "assets/icon.png"
        Window.clearcolor = (0.059, 0.082, 0.071, 1)   # #0F1512
        Builder.load_file(os.path.join(BASE, "ui.kv"))
        self.vault_path = os.path.join(self.user_data_dir, "seyf.skit")
        self._modal = None
        self._paused_at = None

        root = FloatLayout()
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        for cls, name in ((LockScreen, "lock"), (HomeScreen, "home"),
                          (CategoryScreen, "category"), (EditScreen, "edit"),
                          (SettingsScreen, "settings"), (ChangePwScreen, "changepw")):
            self.sm.add_widget(cls(name=name))
        root.add_widget(self.sm)
        self.toast_widget = Toast()
        root.add_widget(self.toast_widget)

        Window.softinput_mode = "below_target"
        Window.bind(on_keyboard=self._on_key)
        self.sm.current = "lock"
        return root

    def on_start(self):
        if SECURE_SCREEN:
            try:
                from android.runnable import run_on_ui_thread
                from jnius import autoclass

                @run_on_ui_thread
                def set_secure():
                    act = autoclass("org.kivy.android.PythonActivity").mActivity
                    act.getWindow().setFlags(8192, 8192)   # FLAG_SECURE
                set_secure()
            except Exception:
                pass

    def on_pause(self):
        self._paused_at = time.time()
        return True

    def on_resume(self):
        clipboard_guard.check_expired()
        if (self.vault is not None and self._paused_at
                and time.time() - self._paused_at > AUTO_LOCK_SECONDS):
            self.lock()
        self._paused_at = None

    # ---- naviqasiya
    def go(self, name, direction="left"):
        self.sm.transition.direction = direction
        self.sm.current = name

    def go_back(self):
        cur = self.sm.current
        if cur in ("category", "settings"):
            self.go("home", "right")
        elif cur == "edit":
            self.go(self.sm.get_screen("edit").back, "right")
        elif cur == "changepw":
            self.go("settings", "right")

    def _on_key(self, window, key, *args):
        if key == 27:                         # Android "geri"
            if self._modal is not None:
                self._modal.dismiss()
                return True
            if self.sm.current in ("home", "lock"):
                return False                  # tətbiqdən çıx
            self.go_back()
            return True
        return False

    # ---- seyf
    def unlocked(self, vault):
        self.vault = vault
        self.refresh_count()
        self.go("home", "left")

    def refresh_count(self):
        self.entry_count = self.vault.count() if self.vault else 0

    def lock(self):
        clipboard_guard.clear_now()
        if self.vault is not None:
            self.vault.lock()
        self.vault = None
        self.entry_count = 0
        self.sm.get_screen("category").wipe()
        self.sm.get_screen("edit").wipe()
        self.go("lock", "right")

    # ---- qeydlər
    def open_category(self, cat):
        self.cat = cat
        self.go("category")

    def new_entry(self, cat):
        self.sm.get_screen("edit").load(None, cat, "category" if cat else "home")
        self.go("edit")

    def edit_entry(self, entry_id):
        self.sm.get_screen("edit").load(entry_id, None, "category")
        self.go("edit")

    def copy_field(self, entry_id, field, label):
        entry = self.vault.get(entry_id) if self.vault else None
        text = entry.get(field, "") if entry else ""
        if not text:
            self.toast("%s boşdur" % label)
            return
        clipboard_guard.copy_secret(text)
        self.toast("%s kopyalandı\n%d saniyədən sonra silinəcək"
                   % (label, clipboard_guard.CLEAR_AFTER))

    # ---- kiçik UI köməkçiləri
    def toast(self, message):
        t = self.toast_widget
        t.text = message
        Animation.cancel_all(t)
        t.opacity = 1
        (Animation(opacity=1, duration=1.8) + Animation(opacity=0, duration=0.4)).start(t)

    def confirm(self, title, message, ok_text, on_ok):
        card = ConfirmCard(title=title, message=message, ok_text=ok_text)
        modal = ModalView(size_hint=(0.9, None), height=dp(250), background="",
                          background_color=(0, 0, 0, 0), overlay_color=(0, 0, 0, 0.65))
        modal.add_widget(card)
        card.bind(on_cancel=lambda *_: modal.dismiss(),
                  on_ok=lambda *_: (modal.dismiss(), on_ok()))
        modal.bind(on_dismiss=lambda *_: setattr(self, "_modal", None))
        self._modal = modal
        modal.open()


if __name__ == "__main__":
    SifrelerKitabcasiApp().run()
