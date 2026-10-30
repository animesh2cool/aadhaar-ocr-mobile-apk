"""
AadhaarScan Mobile - Google ML Kit Edition (v2)

What changed vs v1 (all aimed at a smoother phone experience):
- OCR, image prep and Excel export run on worker threads, so the UI never freezes
- Photos are EXIF-corrected and downscaled before OCR (no sideways text / OOM crashes)
- Gallery picking + saving to Downloads work with Android scoped storage
- Camera permission is requested only when the camera is opened
- Aadhaar number auto-formats as you type and is checked with the Verhoeff checksum
- Scan several cards, review them in a list, export once
- Toasts instead of blocking popups; Android back button closes popups first
- Temporary card images are deleted after use
"""

import datetime
import os
import shutil
import threading
from typing import List

from kivy.utils import platform

IS_ANDROID = platform == "android"

# Desktop aspect ratio simulation (must run before the Window is created)
if not IS_ANDROID:
    from kivy.config import Config
    Config.set("graphics", "width", "400")
    Config.set("graphics", "height", "800")
    Config.set("graphics", "resizable", "1")

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, PopMatrix, PushMatrix, RoundedRectangle, Rotate
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.camera import Camera
from kivy.uix.checkbox import CheckBox
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from aadhaar_utils import (digits_only, export_records, format_aadhaar,
                           is_valid_aadhaar, mask_aadhaar, parse_aadhaar_text,
                           prepare_image)

# ---------------------------------------------------------------- settings
BG = (0.05, 0.07, 0.12, 1)
CARD = (0.09, 0.12, 0.20, 1)
FIELD = (0.14, 0.18, 0.28, 1)
FIELD_FOCUS = (0.19, 0.24, 0.37, 1)
ACCENT = (0.38, 0.40, 0.95, 1)
MUTED = (0.25, 0.30, 0.45, 1)
GREEN = (0.06, 0.72, 0.50, 1)
RED = (0.75, 0.25, 0.28, 1)
DIM = (0.6, 0.7, 0.85, 1)

GENDERS = ("MALE", "FEMALE", "TRANSGENDER")
GENDER_HINT = "Select"

# The phone camera sensor is landscape; Kivy shows it sideways in portrait.
# If the live preview looks rotated on your phone, change -90 to 90.
CAMERA_ROTATION = -90 if IS_ANDROID else 0
CAMERA_RESOLUTION = (1280, 720)

SAMPLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_aadhaar.png")

Window.softinput_mode = "below_target"
Window.clearcolor = BG


def stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def fit_image(img):
    """Scale an Image/Camera to fit its box (works on old and new Kivy)."""
    if hasattr(img, "fit_mode"):
        img.fit_mode = "contain"
    else:
        img.allow_stretch = True
        img.keep_ratio = True


# ---------------------------------------------------------------- widgets
class Card(BoxLayout):
    """Rounded container."""

    def __init__(self, bg=CARD, radius=14, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*bg)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class Caption(Label):
    """Small left-aligned label (text_size is bound so halign really works)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("font_size", "11sp")
        kwargs.setdefault("color", DIM)
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(18))
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "middle")
        super().__init__(**kwargs)
        self.bind(size=lambda inst, size: setattr(inst, "text_size", size))


class FlatButton(Button):
    """Rounded flat button with pressed / disabled tint."""

    def __init__(self, bg=ACCENT, radius=10, **kwargs):
        kwargs.setdefault("font_size", "13sp")
        kwargs.setdefault("bold", True)
        super().__init__(background_normal="", background_down="",
                         background_disabled_normal="", background_disabled_down="",
                         background_color=(0, 0, 0, 0), **kwargs)
        self._bg = bg
        with self.canvas.before:
            self._tint_color = Color(*bg)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._sync, size=self._sync, state=self._tint, disabled=self._tint)

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _tint(self, *_):
        r, g, b, a = self._bg
        if self.disabled:
            self._tint_color.rgba = (r * 0.4, g * 0.4, b * 0.4, a)
        elif self.state == "down":
            self._tint_color.rgba = (r * 0.7, g * 0.7, b * 0.7, a)
        else:
            self._tint_color.rgba = self._bg


class Field(TextInput):
    """Flat single-line input with a focus highlight."""

    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(44))
        kwargs.setdefault("font_size", "14sp")
        kwargs.setdefault("padding", [dp(10), dp(13), dp(10), dp(8)])
        kwargs.setdefault("foreground_color", (1, 1, 1, 1))
        kwargs.setdefault("cursor_color", (0.6, 0.65, 1, 1))
        kwargs.setdefault("hint_text_color", (1, 1, 1, 0.3))
        super().__init__(background_normal="", background_active="",
                         background_color=FIELD, write_tab=False, **kwargs)
        self.bind(focus=lambda inst, focused: setattr(
            inst, "background_color", FIELD_FOCUS if focused else FIELD))


class Toast(Card):
    """Small auto-hiding message. Never steals touches."""

    def __init__(self, text, error=False, **kwargs):
        super().__init__(bg=(0.55, 0.15, 0.18, 1) if error else (0.16, 0.19, 0.30, 1),
                         radius=12, orientation="vertical", padding=(dp(14), dp(10)),
                         size_hint=(0.92, None), height=dp(44),
                         pos_hint={"center_x": 0.5, "y": 0.17}, **kwargs)
        self.label = Label(text=text, font_size="13sp", halign="center", valign="middle",
                           size_hint_y=None)
        self.label.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        self.label.bind(texture_size=self._fit)
        self.add_widget(self.label)

    def _fit(self, _inst, size):
        self.label.height = size[1]
        self.height = size[1] + dp(20)

    def on_touch_down(self, touch):
        return False


class CameraView(FloatLayout):
    """Live viewfinder that shows the landscape sensor feed upright, with a card-shaped guide."""

    def __init__(self, rotation=0, resolution=(1280, 720), **kwargs):
        super().__init__(**kwargs)
        self.rotation = rotation
        self.cam = Camera(index=0, resolution=resolution, play=False, size_hint=(None, None))
        fit_image(self.cam)
        self.add_widget(self.cam)
        with self.canvas.before:
            PushMatrix()
            self._rot = Rotate(angle=rotation, origin=self.center)
        with self.canvas.after:
            PopMatrix()
            Color(1, 1, 1, 0.85)
            self._guide = Line(rounded_rectangle=(0, 0, 0, 0, dp(10)), width=dp(1.8))
        self.bind(pos=self._layout, size=self._layout)

    def _layout(self, *_):
        w, h = self.size
        sideways = abs(self.rotation) % 180 == 90
        self.cam.size = (h, w) if sideways else (w, h)
        self.cam.center = self.center
        self._rot.origin = self.center
        gw = w * 0.92
        gh = gw / 1.586                      # ID-1 card ratio
        if gh > h * 0.92:
            gh = h * 0.92
            gw = gh * 1.586
        self._guide.rounded_rectangle = (self.center_x - gw / 2, self.center_y - gh / 2,
                                         gw, gh, dp(10))

    def start(self):
        self.cam.play = True

    def stop(self):
        self.cam.play = False

    def snapshot(self, path):
        if self.cam.texture is None:
            raise RuntimeError("Camera is still starting - try again in a second")
        self.cam.export_to_png(path)         # unrotated; caller rotates by self.rotation


# ---------------------------------------------------------------- app
class AadhaarMobileApp(App):

    # ------------------------------------------------------------ build
    def build(self):
        self.title = "AadhaarScan"
        self.records: List[dict] = []
        self._busy = False
        self._popup = None
        self._temp_files: List[str] = []
        self._recognizer = None
        self._desktop_ocr = None
        self._chooser = None
        self._dots_event = None
        self._dot_count = 0
        self._status_base = ""
        self._action_buttons: List[Button] = []

        # ML Kit and JNI state (resolved on main UI thread)
        self._mlkit_ready = False
        self._mlkit_error = None
        self._app_loader = None
        self._BitmapFactory = None
        self._InputImage = None
        self._TimeUnit = None
        self._Tasks = None
        self._Environment = None

        self.root_float = FloatLayout()
        main = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        main.add_widget(self._build_header())
        main.add_widget(self._build_body())
        main.add_widget(self._build_actions())
        self.root_float.add_widget(main)

        Window.bind(on_keyboard=self._on_keyboard)
        self._refresh_counts()
        return self.root_float

    def on_start(self):
        if IS_ANDROID:
            Clock.schedule_once(lambda _dt: self._init_android_services(), 0.3)

    def _init_android_services(self):
        try:
            self._init_mlkit()
        except Exception as exc:
            Logger.exception(f"AadhaarScan: Android init error: {exc}")

    def _init_mlkit(self) -> bool:
        """Pre-load all ML Kit and Android classes on the MAIN thread so PyJNIus caches them."""
        if not IS_ANDROID:
            return True
        if self._mlkit_ready and self._recognizer is not None:
            return True
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            if activity:
                self._app_loader = activity.getClassLoader()
                Thread = autoclass("java.lang.Thread")
                Thread.currentThread().setContextClassLoader(self._app_loader)

            self._BitmapFactory = autoclass("android.graphics.BitmapFactory")
            self._InputImage = autoclass("com.google.mlkit.vision.common.InputImage")
            self._TimeUnit = autoclass("java.util.concurrent.TimeUnit")
            self._Tasks = autoclass("com.google.android.gms.tasks.Tasks")
            TextRecognition = autoclass("com.google.mlkit.vision.text.TextRecognition")
            Options = autoclass("com.google.mlkit.vision.text.latin.TextRecognizerOptions")
            self._recognizer = TextRecognition.getClient(Options.DEFAULT_OPTIONS)
            try:
                self._Environment = autoclass("android.os.Environment")
            except Exception:
                pass
            self._mlkit_ready = True
            self._mlkit_error = None
            Logger.info("AadhaarScan: Google ML Kit loaded successfully on main thread")
            return True
        except Exception as exc:
            Logger.exception("AadhaarScan: ML Kit initialization failed on main thread")
            self._mlkit_error = str(exc)
            return False

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        title = Label(text="[b]AadhaarScan[/b] [color=818cf8]ML Kit[/color]", markup=True,
                      font_size="18sp", halign="left", valign="middle")
        title.bind(size=lambda inst, size: setattr(inst, "text_size", size))
        header.add_widget(title)
        if os.path.exists(SAMPLE_PATH):
            header.add_widget(FlatButton(text="Sample", size_hint=(None, 1), width=dp(70),
                                         bg=MUTED, font_size="12sp",
                                         on_release=self.load_sample))
        self.btn_list = FlatButton(text="List (0)", size_hint=(None, 1), width=dp(84),
                                   bg=MUTED, font_size="12sp", on_release=self.show_records)
        header.add_widget(self.btn_list)
        return header

    def _build_body(self):
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None,
                            padding=(0, 0, 0, dp(8)))
        content.bind(minimum_height=content.setter("height"))

        # preview
        preview = Card(bg=(0.08, 0.11, 0.18, 1), padding=dp(6), size_hint_y=None, height=dp(190))
        stack = FloatLayout()
        self.preview_hint = Label(text="Card preview appears here", font_size="12sp",
                                  color=DIM, pos_hint={"center_x": 0.5, "center_y": 0.5})
        self.img_preview = Image(source="")
        fit_image(self.img_preview)
        stack.add_widget(self.preview_hint)
        stack.add_widget(self.img_preview)
        preview.add_widget(stack)
        content.add_widget(preview)

        # status
        self.status = Label(text="Tap Camera or Gallery to scan a card", font_size="12sp",
                            color=DIM, size_hint_y=None, height=dp(24))
        content.add_widget(self.status)

        # form
        form = Card(bg=CARD, orientation="vertical", padding=dp(12), spacing=dp(6),
                    size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        top = BoxLayout(size_hint_y=None, height=dp(30))
        top.add_widget(Caption(text="DETAILS", height=dp(30)))
        top.add_widget(FlatButton(text="Clear", size_hint=(None, None), size=(dp(64), dp(30)),
                                  bg=MUTED, font_size="11sp", on_release=self.clear_form))
        form.add_widget(top)

        form.add_widget(Caption(text="FULL NAME"))
        self.input_name = Field(hint_text="e.g. RAHUL KUMAR")
        form.add_widget(self.input_name)

        form.add_widget(Caption(text="AADHAAR NUMBER"))
        self.input_aadhaar = Field(hint_text="XXXX XXXX XXXX", font_size="17sp",
                                   input_type="number", height=dp(48),
                                   foreground_color=(1, 0.8, 0.8, 1))
        self.input_aadhaar.bind(text=self._on_aadhaar_text)
        form.add_widget(self.input_aadhaar)
        self.validity = Caption(text="", markup=True)
        form.add_widget(self.validity)

        row = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(66))
        dob_col = BoxLayout(orientation="vertical", spacing=dp(2))
        dob_col.add_widget(Caption(text="DATE OF BIRTH"))
        self.input_dob = Field(hint_text="DD/MM/YYYY", font_size="13sp")
        dob_col.add_widget(self.input_dob)
        gen_col = BoxLayout(orientation="vertical", spacing=dp(2))
        gen_col.add_widget(Caption(text="GENDER"))
        self.input_gender = Spinner(text=GENDER_HINT, values=GENDERS, font_size="13sp",
                                    size_hint_y=None, height=dp(44), background_normal="",
                                    background_down="", background_color=FIELD)
        gen_col.add_widget(self.input_gender)
        row.add_widget(dob_col)
        row.add_widget(gen_col)
        form.add_widget(row)

        mask_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.mask_box = CheckBox(size_hint=(None, 1), width=dp(36), active=False)
        mask_row.add_widget(self.mask_box)
        mask_row.add_widget(Caption(text="Mask number in Excel (XXXX XXXX 1234)", height=dp(36)))
        form.add_widget(mask_row)

        content.add_widget(form)
        scroll.add_widget(content)
        return scroll

    def _build_actions(self):
        box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, height=dp(100))
        row1 = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(44))
        self.btn_cam = FlatButton(text="Camera", bg=ACCENT, on_release=self.open_camera_view)
        self.btn_gal = FlatButton(text="Gallery", bg=MUTED, on_release=self.open_gallery)
        row1.add_widget(self.btn_cam)
        row1.add_widget(self.btn_gal)
        row2 = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        self.btn_add = FlatButton(text="Add to list", bg=MUTED, on_release=self.add_to_list)
        self.btn_export = FlatButton(text="Export Excel", bg=GREEN,
                                     on_release=self.export_to_excel)
        row2.add_widget(self.btn_add)
        row2.add_widget(self.btn_export)
        box.add_widget(row1)
        box.add_widget(row2)
        self._action_buttons = [self.btn_cam, self.btn_gal, self.btn_add, self.btn_export]
        return box

    # ------------------------------------------------------------ lifecycle
    def on_pause(self):
        return True

    def on_stop(self):
        self._purge_temp()
        if self._recognizer is not None:
            try:
                self._recognizer.close()
            except Exception:
                pass

    def _on_keyboard(self, _window, key, *_args):
        if key == 27 and self._popup is not None:      # Android back / Esc
            self._popup.dismiss()
            return True
        return False

    # ------------------------------------------------------------ small UI helpers
    def toast(self, text, error=False, duration=2.6):
        t = Toast(text, error=error)
        t.opacity = 0
        self.root_float.add_widget(t)
        Animation(opacity=1, duration=0.15).start(t)

        def hide(_dt):
            anim = Animation(opacity=0, duration=0.3)
            anim.bind(on_complete=lambda *_: self.root_float.remove_widget(t))
            anim.start(t)

        Clock.schedule_once(hide, duration)

    def set_status(self, text, error=False):
        self.status.text = text
        self.status.color = (1, 0.55, 0.55, 1) if error else DIM

    def _set_busy(self, busy, text=""):
        self._busy = busy
        for btn in self._action_buttons:
            btn.disabled = busy
        if self._dots_event is not None:
            self._dots_event.cancel()
            self._dots_event = None
        if busy:
            self._status_base = text
            self._dot_count = 0
            self.set_status(text)
            self._dots_event = Clock.schedule_interval(self._tick, 0.35)
        elif text:
            self.set_status(text)

    def _tick(self, _dt):
        self._dot_count = (self._dot_count + 1) % 4
        self.status.text = self._status_base + "." * self._dot_count

    def _open_popup(self, popup):
        self._popup = popup
        popup.bind(on_dismiss=self._popup_closed)
        popup.open()

    def _popup_closed(self, popup):
        if self._popup is popup:
            self._popup = None

    def show_message(self, title, message):
        body = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        lbl = Label(text=message, font_size="13sp", halign="center", valign="middle")
        lbl.bind(size=lambda inst, size: setattr(inst, "text_size", size))
        body.add_widget(lbl)
        ok = FlatButton(text="OK", size_hint_y=None, height=dp(44))
        body.add_widget(ok)
        popup = Popup(title=title, content=body, size_hint=(0.9, 0.4))
        ok.bind(on_release=popup.dismiss)
        self._open_popup(popup)

    def _refresh_counts(self):
        n = len(self.records)
        self.btn_list.text = f"List ({n})"
        self.btn_export.text = f"Export Excel ({n})" if n else "Export Excel"

    # ------------------------------------------------------------ files / temp
    def _cache_dir(self):
        path = os.path.join(self.user_data_dir, "scan_cache")
        os.makedirs(path, exist_ok=True)
        return path

    def _export_dir(self):
        if not IS_ANDROID:
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            if os.path.isdir(downloads):
                return downloads
        path = os.path.join(self.user_data_dir, "exports")
        os.makedirs(path, exist_ok=True)
        return path

    def _track_temp(self, path):
        if path and path not in self._temp_files:
            self._temp_files.append(path)

    def _discard(self, path):
        try:
            os.remove(path)
        except OSError:
            pass
        if path in self._temp_files:
            self._temp_files.remove(path)

    def _purge_temp(self):
        for path in list(self._temp_files):
            self._discard(path)

    # ------------------------------------------------------------ form handling
    def _on_aadhaar_text(self, inst, value):
        digits = digits_only(value)[:12]
        pretty = format_aadhaar(digits)
        if pretty != value:
            inst.text = pretty
            Clock.schedule_once(lambda _dt: setattr(inst, "cursor", (len(pretty), 0)), 0)
            return
        if not digits:
            self.validity.text = ""
        elif len(digits) < 12:
            self.validity.text = f"{len(digits)}/12 digits"
        elif is_valid_aadhaar(digits):
            self.validity.text = "[color=34d399]Checksum valid[/color]"
        else:
            self.validity.text = "[color=fbbf24]Checksum failed - re-check the digits[/color]"

    def _fill_form(self, parsed):
        self.input_name.text = parsed.get("name") or ""
        self.input_aadhaar.text = parsed.get("aadhaar_number") or ""
        self.input_dob.text = parsed.get("dob") or ""
        gender = parsed.get("gender") or ""
        self.input_gender.text = gender if gender in GENDERS else GENDER_HINT

    def _current_record(self):
        digits = digits_only(self.input_aadhaar.text)
        name = self.input_name.text.strip()
        if not digits and not name:
            return None
        gender = self.input_gender.text
        return {
            "aadhaar": format_aadhaar(digits),
            "name": name,
            "dob": self.input_dob.text.strip(),
            "gender": gender if gender in GENDERS else "",
            "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def clear_form(self, *_):
        self._fill_form({})
        self.img_preview.source = ""
        self.preview_hint.opacity = 1
        self._purge_temp()
        if not self._busy:
            self.set_status("Tap Camera or Gallery to scan a card")

    def add_to_list(self, *_, quiet=False):
        rec = self._current_record()
        if rec is None:
            if not quiet:
                self.toast("Nothing to add yet - scan a card or type the details")
            return False
        key = (digits_only(rec["aadhaar"]), rec["name"].lower())
        if any((digits_only(r["aadhaar"]), r["name"].lower()) == key for r in self.records):
            if not quiet:
                self.toast("Already in the list")
            return True
        self.records.append(rec)
        self._refresh_counts()
        self.clear_form()
        if not quiet:
            warn = ""
            if rec["aadhaar"] and not is_valid_aadhaar(rec["aadhaar"]):
                warn = " (checksum failed - please verify)"
            self.toast(f"Added - {len(self.records)} in list{warn}")
        return True

    def show_records(self, *_):
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        popup = Popup(title=f"Scanned cards ({len(self.records)})", content=body,
                      size_hint=(0.95, 0.8))
        if not self.records:
            body.add_widget(Label(text="No cards in the list yet.\nScan one and tap 'Add to list'.",
                                  halign="center", font_size="13sp", color=DIM))
        else:
            sv = ScrollView(do_scroll_x=False)
            grid = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            for i, rec in enumerate(self.records):
                row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
                text = (f"{i + 1}. {rec['name'] or '(no name)'}\n"
                        f"[size=11sp][color=9fb3d9]{mask_aadhaar(rec['aadhaar'])}[/color][/size]")
                lbl = Label(text=text, markup=True, halign="left", valign="middle",
                            font_size="13sp")
                lbl.bind(size=lambda inst, size: setattr(inst, "text_size", size))
                row.add_widget(lbl)
                row.add_widget(FlatButton(
                    text="Delete", size_hint=(None, 1), width=dp(66), bg=RED, font_size="11sp",
                    on_release=lambda _b, idx=i: self._delete_record(idx, popup)))
                grid.add_widget(row)
            sv.add_widget(grid)
            body.add_widget(sv)

        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        if self.records:
            buttons.add_widget(FlatButton(text="Clear all", bg=RED,
                                          on_release=lambda _b: self._clear_records(popup)))
        close = FlatButton(text="Close", bg=MUTED)
        close.bind(on_release=popup.dismiss)
        buttons.add_widget(close)
        body.add_widget(buttons)
        self._open_popup(popup)

    def _delete_record(self, idx, popup):
        if 0 <= idx < len(self.records):
            del self.records[idx]
        self._refresh_counts()
        popup.dismiss(animation=False)
        self.show_records()

    def _clear_records(self, popup):
        self.records.clear()
        self._refresh_counts()
        popup.dismiss()

    # ------------------------------------------------------------ input: camera
    def _with_camera_permission(self, then):
        if not IS_ANDROID:
            then()
            return
        try:
            from android.permissions import Permission, check_permission, request_permissions
        except Exception as exc:                      # pragma: no cover
            Logger.warning(f"AadhaarScan: permissions API unavailable: {exc}")
            then()
            return
        if check_permission(Permission.CAMERA):
            then()
            return

        def on_result(_perms, grants):
            if grants and all(grants):
                Clock.schedule_once(lambda _dt: then())
            else:
                Clock.schedule_once(lambda _dt: self.toast(
                    "Camera permission denied - use Gallery instead", error=True))

        request_permissions([Permission.CAMERA], on_result)

    def open_camera_view(self, *_):
        if self._busy:
            return
        self._with_camera_permission(self._show_camera)

    def _show_camera(self):
        try:
            view = CameraView(rotation=CAMERA_ROTATION, resolution=CAMERA_RESOLUTION)
        except Exception as exc:
            Logger.exception("AadhaarScan: camera init failed")
            self.toast(f"Camera unavailable: {exc}", error=True)
            return

        body = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        body.add_widget(view)
        body.add_widget(Caption(text="Fit the card inside the frame and hold steady",
                                halign="center", height=dp(20)))
        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        capture = FlatButton(text="Capture", bg=ACCENT, font_size="14sp")
        close = FlatButton(text="Close", bg=MUTED)
        buttons.add_widget(capture)
        buttons.add_widget(close)
        body.add_widget(buttons)

        popup = Popup(title="Scan Aadhaar card", content=body, size_hint=(0.96, 0.9),
                      auto_dismiss=False)
        popup.bind(on_dismiss=lambda *_: view.stop())

        def do_capture(*_):
            path = os.path.join(self._cache_dir(), f"snap_{stamp()}.png")
            try:
                view.snapshot(path)
            except Exception as exc:
                self.toast(str(exc), error=True)
                return
            popup.dismiss()
            self.process_image_path(path, owned=True, rotate=view.rotation)

        capture.bind(on_release=do_capture)
        close.bind(on_release=popup.dismiss)
        self._open_popup(popup)
        Clock.schedule_once(lambda _dt: view.start(), 0.15)

    # ------------------------------------------------------------ input: gallery / files
    def open_gallery(self, *_):
        if self._busy:
            return
        if IS_ANDROID:
            try:
                from androidstorage4kivy import Chooser
                self._chooser = Chooser(self._on_gallery_result)
                self._chooser.choose_content("image/*")
                return
            except Exception as exc:
                Logger.warning(f"AadhaarScan: system picker unavailable ({exc}); using fallback")
                self.toast("Gallery picker not installed - using file browser")
        self._open_file_chooser()

    def _on_gallery_result(self, uris):
        if not uris:
            return
        uri = uris[0]

        def load():
            from androidstorage4kivy import SharedStorage
            return SharedStorage().copy_from_shared(uri)

        Clock.schedule_once(lambda _dt: self._run_scan(load, owned=True))

    def _open_file_chooser(self):
        from kivy.uix.filechooser import FileChooserListView
        start = self.user_data_dir if IS_ANDROID else os.path.expanduser("~")
        chooser = FileChooserListView(path=start, filters=["*.png", "*.jpg", "*.jpeg", "*.webp"])
        body = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        body.add_widget(chooser)
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        select = FlatButton(text="Select", bg=ACCENT)
        cancel = FlatButton(text="Cancel", bg=MUTED)
        buttons.add_widget(select)
        buttons.add_widget(cancel)
        body.add_widget(buttons)
        popup = Popup(title="Select Aadhaar image", content=body, size_hint=(0.95, 0.88))

        def on_select(*_):
            if chooser.selection:
                path = chooser.selection[0]
                popup.dismiss()
                self.process_image_path(path)

        select.bind(on_release=on_select)
        cancel.bind(on_release=popup.dismiss)
        self._open_popup(popup)

    def load_sample(self, *_):
        if os.path.exists(SAMPLE_PATH):
            self.process_image_path(SAMPLE_PATH)
        else:
            self.toast("Sample image not found", error=True)

    # ------------------------------------------------------------ scanning pipeline
    def process_image_path(self, path, owned=False, rotate=0):
        """owned=True means we created `path` (camera/gallery copy), so it gets deleted after use."""
        self._run_scan(lambda: path, owned=owned, rotate=rotate)

    def _run_scan(self, loader, owned=False, rotate=0):
        if self._busy:
            return
        if IS_ANDROID and not self._mlkit_ready:
            if not self._init_mlkit():
                self.toast(f"ML Kit unavailable: {self._mlkit_error}", error=True)
                return
        self._purge_temp()
        self._set_busy(True, "Preparing image")
        threading.Thread(target=self._scan_worker, args=(loader, owned, rotate),
                         daemon=True).start()

    def _scan_worker(self, loader, owned, rotate):
        """Runs off the UI thread. Only touch widgets via Clock.schedule_once."""
        if IS_ANDROID and self._app_loader:
            try:
                from jnius import autoclass
                Thread = autoclass("java.lang.Thread")
                Thread.currentThread().setContextClassLoader(self._app_loader)
            except Exception as exc:
                Logger.warning(f"AadhaarScan: could not set worker thread classloader: {exc}")
        try:
            src = loader()
            if not src or not os.path.exists(src):
                raise FileNotFoundError("Image file not found")
            if owned:
                self._track_temp(src)
            prepared = prepare_image(src, self._cache_dir(), rotate_deg=rotate)
            if prepared != src:
                self._track_temp(prepared)
                if owned:
                    self._discard(src)          # drop the big original right away
            Clock.schedule_once(lambda _dt: self._show_preview(prepared))
            Clock.schedule_once(lambda _dt: self._update_busy_text("Reading text"))
            lines = self._recognise(prepared)
            parsed = parse_aadhaar_text(lines)
            Clock.schedule_once(lambda _dt: self._on_scan_done(parsed, len(lines)))
        except Exception as exc:
            Logger.exception("AadhaarScan: scan failed")
            message = str(exc) or exc.__class__.__name__
            Clock.schedule_once(lambda _dt: self._on_scan_error(message))

    def _update_busy_text(self, text):
        if self._busy:
            self._status_base = text

    def _show_preview(self, path):
        self.img_preview.source = path
        self.img_preview.reload()
        self.preview_hint.opacity = 0

    def _on_scan_done(self, parsed, line_count):
        self._set_busy(False)
        self._fill_form(parsed)
        if parsed["aadhaar_number"] or parsed["name"]:
            self.set_status("Scan complete - please review the fields")
        elif line_count == 0:
            self.set_status("No text found. Try better light and hold steady.", error=True)
        else:
            self.set_status("Text found but no card details detected - fill in manually.",
                            error=True)

    def _on_scan_error(self, message):
        self._set_busy(False)
        self.set_status("Scan failed", error=True)
        self.toast(message, error=True, duration=4)

    # ------------------------------------------------------------ OCR engines
    def _recognise(self, path: str) -> List[str]:
        return self._mlkit_lines(path) if IS_ANDROID else self._desktop_lines(path)

    def _mlkit_lines(self, path: str) -> List[str]:
        if not self._mlkit_ready or self._recognizer is None:
            raise RuntimeError(f"ML Kit engine not ready: {self._mlkit_error or 'uninitialized'}")

        bitmap = self._BitmapFactory.decodeFile(path)
        if bitmap is None:
            raise RuntimeError("Could not decode the image")
        try:
            image = self._InputImage.fromBitmap(bitmap, 0)
            task = self._recognizer.process(image)
            # We're on a worker thread, so blocking here is fine - with a timeout.
            result = getattr(self._Tasks, "await")(task, 25, self._TimeUnit.SECONDS)
            text = result.getText() or ""
        finally:
            bitmap.recycle()
        return [ln.strip() for ln in text.split("\n") if ln.strip()]

    def _desktop_lines(self, path: str) -> List[str]:
        try:
            if self._desktop_ocr is None:
                from aadhaar_ocr import AadhaarOCR
                self._desktop_ocr = AadhaarOCR(languages=["en", "hi"], use_gpu=False,
                                               verbose=False)
        except ImportError:
            raise RuntimeError("Desktop OCR module 'aadhaar_ocr' not found - "
                               "OCR runs on Android only")
        return self._desktop_ocr.extract_text(path)

    # ------------------------------------------------------------ export
    def export_to_excel(self, *_):
        if self._busy:
            return
        if self._current_record() is not None:
            self.add_to_list(quiet=True)        # include whatever is on screen
        if not self.records:
            self.toast("Nothing to export - scan a card or enter details first")
            return
        records = [dict(r) for r in self.records]
        mask = self.mask_box.active
        self._set_busy(True, "Creating Excel file")
        threading.Thread(target=self._export_worker, args=(records, mask), daemon=True).start()

    def _export_worker(self, records, mask):
        if IS_ANDROID and self._app_loader:
            try:
                from jnius import autoclass
                Thread = autoclass("java.lang.Thread")
                Thread.currentThread().setContextClassLoader(self._app_loader)
            except Exception:
                pass
        try:
            private = os.path.join(self._export_dir(), f"Aadhaar_Data_{stamp()}.xlsx")
            export_records(records, private, mask=mask)
            where = self._publish_file(private)
            Clock.schedule_once(lambda _dt: self._on_export_done(where, len(records)))
        except Exception as exc:
            Logger.exception("AadhaarScan: export failed")
            message = str(exc) or exc.__class__.__name__
            Clock.schedule_once(lambda _dt: self._on_export_error(message))

    def _publish_file(self, private_path: str) -> str:
        """Make the file visible to the user. Returns a readable location."""
        if IS_ANDROID:
            try:                                     # Android 10+ (scoped storage) way
                from androidstorage4kivy import SharedStorage
                env = self._Environment
                if env is None:
                    from jnius import autoclass
                    env = autoclass("android.os.Environment")
                SharedStorage().copy_to_shared(private_path,
                                               collection=env.DIRECTORY_DOWNLOADS)
                where = "Downloads/" + os.path.basename(private_path)
                self._discard(private_path)
                return where
            except Exception as exc:
                Logger.warning(f"AadhaarScan: shared-storage save failed: {exc}")
            try:                                     # legacy fallback (Android 9 and below)
                from android.storage import primary_external_storage_path
                dest = os.path.join(primary_external_storage_path(), "Download",
                                    os.path.basename(private_path))
                shutil.copy2(private_path, dest)
                os.remove(private_path)
                return dest
            except Exception as exc:
                Logger.warning(f"AadhaarScan: legacy save failed: {exc}")
        return private_path

    def _on_export_done(self, where, count):
        self._set_busy(False, "Excel file saved")
        self.show_message("Export successful", f"{count} record(s) saved to:\n\n{where}")

    def _on_export_error(self, message):
        self._set_busy(False, "Export failed")
        self.toast(message, error=True, duration=4)


if __name__ == "__main__":
    AadhaarMobileApp().run()
