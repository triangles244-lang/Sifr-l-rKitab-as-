"""Şifrələr Kitabçası - şifrələmə nüvəsi.

Fayl formatı (hamısı bir faylda, yalnız master parolla açılır):

    MAGIC(4) | version(1) | log2(N)(1) | r(1) | p(1) | salt(16) | nonce(12) | şifrəli mətn + tag(16)

Başlığın özü (ciphertext-dən əvvəlki hissə) AES-GCM-də "AAD" kimi qorunur,
yəni başlıqda dəyişiklik edilsə fayl açılmır.

Açar: master paroldan scrypt ilə törədilir (32 bayt). Şifrələmə: AES-256-GCM.
İki kitabxanadan hansı varsa işlədilir (nəticə eynidir, fayllar uyğundur):
  * cryptography
  * pycryptodome
"""
import hmac
import json
import os
import secrets
import shutil
import time
import unicodedata

try:  # 1-ci seçim
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.exceptions import InvalidTag
    _BACKEND = "cryptography"
except ImportError:  # 2-ci seçim (Android build üçün daha asandır)
    from Crypto.Cipher import AES as _AES
    from Crypto.Protocol.KDF import scrypt as _scrypt
    _BACKEND = "pycryptodome"

MAGIC = b"SKIT"
VERSION = 1
SALT_LEN = 16
NONCE_LEN = 12
TAG_LEN = 16
LOG_N = 15          # N = 32768 (~32 MB yaddaş). Telefonda təxminən 0.5-1.5 san.
R = 8
P = 1
MAX_LOG_N = 20      # zədəli/saxta fayl yaddaşı doldurmasın deyə yuxarı hədd
HEADER_LEN = len(MAGIC) + 4 + SALT_LEN + NONCE_LEN

CATEGORIES = ("web", "game", "mail")


class VaultError(Exception):
    pass


class WrongPassword(VaultError):
    """Master parol səhvdir (və ya fayl dəyişdirilib)."""


class CorruptFile(VaultError):
    """Fayl bizim formatda deyil və ya zədəlidir."""


# ----------------------------------------------------------- aşağı səviyyə
def _norm(password):
    return unicodedata.normalize("NFKC", password).encode("utf-8")


def _derive(password, salt, log_n=LOG_N, r=R, p=P):
    pw = _norm(password)
    if _BACKEND == "cryptography":
        return Scrypt(salt=salt, length=32, n=1 << log_n, r=r, p=p).derive(pw)
    return _scrypt(pw, salt, 32, N=1 << log_n, r=r, p=p)


def _encrypt(key, nonce, plaintext, aad):
    if _BACKEND == "cryptography":
        return AESGCM(key).encrypt(nonce, plaintext, aad)
    c = _AES.new(key, _AES.MODE_GCM, nonce=nonce, mac_len=TAG_LEN)
    c.update(aad)
    ct, tag = c.encrypt_and_digest(plaintext)
    return ct + tag


def _decrypt(key, nonce, blob, aad):
    if len(blob) < TAG_LEN:
        raise CorruptFile("Fayl çox qısadır.")
    try:
        if _BACKEND == "cryptography":
            return AESGCM(key).decrypt(nonce, blob, aad)
        c = _AES.new(key, _AES.MODE_GCM, nonce=nonce, mac_len=TAG_LEN)
        c.update(aad)
        return c.decrypt_and_verify(blob[:-TAG_LEN], blob[-TAG_LEN:])
    except Exception as exc:  # InvalidTag / ValueError
        raise WrongPassword("Master parol səhvdir.") from exc


def _header(log_n, r, p, salt, nonce):
    return MAGIC + bytes([VERSION, log_n, r, p]) + salt + nonce


# ------------------------------------------------------------------ Vault
class Vault:
    """Açılmış (deşifrə olunmuş) seyf. Yaddaşda açar və qeydlər saxlanır."""

    def __init__(self, path, key, salt, params, data):
        self.path = path
        self._key = key
        self._salt = salt
        self._params = params          # (log_n, r, p)
        self.data = data

    # ---- yaratmaq / açmaq
    @staticmethod
    def exists(path):
        return os.path.isfile(path)

    @classmethod
    def create(cls, path, password):
        if not password:
            raise VaultError("Master parol boş ola bilməz.")
        salt = secrets.token_bytes(SALT_LEN)
        params = (LOG_N, R, P)
        key = _derive(password, salt, *params)
        v = cls(path, key, salt, params, {"v": 1, "entries": []})
        v.save()
        return v

    @classmethod
    def open(cls, path, password):
        with open(path, "rb") as fh:
            raw = fh.read()
        if len(raw) < HEADER_LEN + TAG_LEN or raw[:4] != MAGIC:
            raise CorruptFile("Bu fayl Şifrələr Kitabçası faylı deyil.")
        version, log_n, r, p = raw[4], raw[5], raw[6], raw[7]
        if version != VERSION:
            raise CorruptFile("Fayl versiyası dəstəklənmir: %d" % version)
        if not (10 <= log_n <= MAX_LOG_N) or r == 0 or r > 32 or p == 0 or p > 8:
            raise CorruptFile("Faylın başlığı zədəlidir.")
        salt = raw[8:8 + SALT_LEN]
        nonce = raw[8 + SALT_LEN:HEADER_LEN]
        key = _derive(password, salt, log_n, r, p)
        plain = _decrypt(key, nonce, raw[HEADER_LEN:], raw[:HEADER_LEN])
        try:
            data = json.loads(plain.decode("utf-8"))
        except ValueError as exc:
            raise CorruptFile("Məzmun oxuna bilmədi.") from exc
        return cls(path, key, salt, (log_n, r, p), data)

    # ---- saxlamaq (atomik: əvvəl müvəqqəti fayla, sonra əvəz et)
    def save(self):
        nonce = secrets.token_bytes(NONCE_LEN)       # hər yazmada yeni nonce
        header = _header(*self._params, self._salt, nonce)
        plain = json.dumps(self.data, ensure_ascii=False).encode("utf-8")
        blob = header + _encrypt(self._key, nonce, plain, header)

        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        if os.path.isfile(self.path):                # bir ədəd ehtiyat nüsxə
            try:
                shutil.copy2(self.path, self.path + ".bak")
            except OSError:
                pass
        os.replace(tmp, self.path)

    # ---- master parol
    def check_password(self, password):
        key = _derive(password, self._salt, *self._params)
        return hmac.compare_digest(key, self._key)

    def change_password(self, new_password):
        if not new_password:
            raise VaultError("Yeni master parol boş ola bilməz.")
        salt = secrets.token_bytes(SALT_LEN)
        self._salt = salt
        self._params = (LOG_N, R, P)
        self._key = _derive(new_password, salt, *self._params)
        self.save()
        # köhnə parolla açıla bilən .bak qalmasın
        for extra in (self.path + ".bak",):
            try:
                os.remove(extra)
            except OSError:
                pass

    # ---- qeydlər
    def entries(self, category=None):
        items = self.data["entries"]
        if category:
            items = [e for e in items if e.get("cat") == category]
        return sorted(items, key=lambda e: e.get("title", "").casefold())

    def count(self, category=None):
        return len(self.entries(category))

    def get(self, entry_id):
        for e in self.data["entries"]:
            if e["id"] == entry_id:
                return e
        return None

    def add(self, category, title, user, password):
        if category not in CATEGORIES:
            raise VaultError("Naməlum bölmə.")
        now = int(time.time())
        entry = {
            "id": secrets.token_hex(8), "cat": category, "title": title,
            "user": user, "pw": password, "created": now, "modified": now,
        }
        self.data["entries"].append(entry)
        self.save()
        return entry["id"]

    def update(self, entry_id, **fields):
        e = self.get(entry_id)
        if e is None:
            raise VaultError("Qeyd tapılmadı.")
        for k in ("cat", "title", "user", "pw"):
            if k in fields:
                e[k] = fields[k]
        e["modified"] = int(time.time())
        self.save()

    def delete(self, entry_id):
        before = len(self.data["entries"])
        self.data["entries"] = [e for e in self.data["entries"] if e["id"] != entry_id]
        if len(self.data["entries"]) != before:
            self.save()

    def lock(self):
        """Açarı və qeydləri referansdan çıxarır (Python tam silməyi zəmanət vermir)."""
        self._key = b""
        self.data = {"v": 1, "entries": []}


def generate_password(length=18):
    alphabet = ("abcdefghijkmnopqrstuvwxyz" "ABCDEFGHJKLMNPQRSTUVWXYZ"
                "23456789" "!@#$%^&*-_?")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*-_?" for c in pw)):
            return pw
