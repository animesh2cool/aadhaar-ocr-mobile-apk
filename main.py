"""
Modern Offline Aadhaar Card OCR Mobile Application
Features:
- Google ML Kit Text Recognition on Android (100% on-device & offline via PyJNIus)
- Camera & Gallery picker via Plyer
- Modern Dynamic DPI & Adaptive High-Resolution Screen Rendering
- Offline Excel (.xlsx) generator using openpyxl
"""

import os
import sys
import re
import datetime
from typing import Dict, Any, List

from kivy.utils import platform

# Modern Render Fix: Only force fixed window on desktop/laptop.
# On Android, allow native full-screen resolution and high-DPI scaling.
if platform != 'android':
    from kivy.config import Config
    Config.set('graphics', 'width', '400')
    Config.set('graphics', 'height', '800')
    Config.set('graphics', 'resizable', '1')

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.clock import Clock

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Configure keyboard behavior on Android
Window.softinput_mode = 'below_target'
Window.clearcolor = (0.05, 0.07, 0.12, 1.0)


class StyledCard(BoxLayout):
    """A sleek rounded container card for mobile screens."""
    def __init__(self, bg_color=(0.10, 0.13, 0.22, 1.0), radius=16, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.radius = radius
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[dp(self.radius)])
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, *args):
        self.rect.size = self.size
        self.rect.pos = self.pos


class AadhaarMobileApp(App):
    def build(self):
        self.title = "AadhaarScan Mobile"
        self.current_image_path = None

        # Request Android Runtime Permissions at Launch
        if platform == 'android':
            self.request_android_permissions()

        # Root Layout with Canvas Background Fix
        root = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        with root.canvas.before:
            Color(0.05, 0.07, 0.12, 1.0)
            self.bg_rect = Rectangle(size=root.size, pos=root.pos)
        root.bind(size=self._update_bg, pos=self._update_bg)

        # 1. Header Bar
        header = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        header_title = Label(
            text="[b]AadhaarScan[/b] [color=818cf8]ML Kit[/color]",
            markup=True,
            font_size='20sp',
            halign='left',
            valign='middle'
        )
        header_title.bind(size=header_title.setter('text_size'))
        header.add_widget(header_title)

        sample_btn = Button(
            text="⚡ Sample",
            size_hint=(None, 1),
            width=dp(95),
            background_normal='',
            background_color=(0.38, 0.40, 0.95, 0.85),
            font_size='12sp',
            bold=True
        )
        sample_btn.bind(on_press=self.load_sample)
        header.add_widget(sample_btn)
        root.add_widget(header)

        # 2. Main Scrollable Viewport
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation='vertical', spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        # Card Preview Container
        preview_card = StyledCard(
            bg_color=(0.08, 0.11, 0.18, 1.0),
            orientation='vertical',
            padding=dp(8),
            size_hint_y=None,
            height=dp(210)
        )
        self.img_preview = Image(
            source='',
            allow_stretch=True,
            keep_ratio=True
        )
        preview_card.add_widget(self.img_preview)
        content.add_widget(preview_card)

        # Status Label
        self.status_label = Label(
            text="Tap 'Open Camera' or 'Gallery' to scan card",
            font_size='12sp',
            color=(0.65, 0.75, 0.85, 1),
            size_hint_y=None,
            height=dp(26)
        )
        content.add_widget(self.status_label)

        # Form Fields Card
        form_card = StyledCard(
            bg_color=(0.09, 0.12, 0.20, 1.0),
            orientation='vertical',
            padding=dp(14),
            spacing=dp(8),
            size_hint_y=None
        )
        form_card.bind(minimum_height=form_card.setter('height'))

        # Full Name Field
        form_card.add_widget(Label(text="FULL NAME", font_size='11sp', color=(0.6, 0.7, 0.85, 1), size_hint_y=None, height=dp(18), halign='left'))
        self.input_name = TextInput(
            hint_text="e.g. RAHUL KUMAR",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
            font_size='14sp',
            background_color=(0.14, 0.18, 0.28, 1),
            foreground_color=(1, 1, 1, 1)
        )
        form_card.add_widget(self.input_name)

        # Aadhaar Number Field
        form_card.add_widget(Label(text="AADHAAR NUMBER", font_size='11sp', color=(0.6, 0.7, 0.85, 1), size_hint_y=None, height=dp(18), halign='left'))
        self.input_aadhaar = TextInput(
            hint_text="XXXX XXXX XXXX",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            font_size='16sp',
            bold=True,
            background_color=(0.18, 0.12, 0.15, 1),
            foreground_color=(1, 0.55, 0.55, 1)
        )
        form_card.add_widget(self.input_aadhaar)

        # DOB & Gender Columns
        row_cols = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(68))
        
        dob_col = BoxLayout(orientation='vertical', spacing=dp(4))
        dob_col.add_widget(Label(text="DATE OF BIRTH", font_size='11sp', color=(0.6, 0.7, 0.85, 1), size_hint_y=None, height=dp(18)))
        self.input_dob = TextInput(
            hint_text="DD/MM/YYYY",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
            font_size='13sp',
            background_color=(0.14, 0.18, 0.28, 1),
            foreground_color=(1, 1, 1, 1)
        )
        dob_col.add_widget(self.input_dob)
        row_cols.add_widget(dob_col)

        gender_col = BoxLayout(orientation='vertical', spacing=dp(4))
        gender_col.add_widget(Label(text="GENDER", font_size='11sp', color=(0.6, 0.7, 0.85, 1), size_hint_y=None, height=dp(18)))
        self.input_gender = TextInput(
            hint_text="MALE / FEMALE",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
            font_size='13sp',
            background_color=(0.14, 0.18, 0.28, 1),
            foreground_color=(1, 1, 1, 1)
        )
        gender_col.add_widget(self.input_gender)
        row_cols.add_widget(gender_col)

        form_card.add_widget(row_cols)
        content.add_widget(form_card)

        scroll.add_widget(content)
        root.add_widget(scroll)

        # 3. Action Buttons Section
        actions = BoxLayout(orientation='vertical', spacing=dp(8), size_hint_y=None, height=dp(105))
        
        # Row 1: Camera + Gallery
        row_inputs = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(46))
        
        btn_cam = Button(
            text="📷 Open Camera",
            background_normal='',
            background_color=(0.38, 0.40, 0.95, 1.0),
            font_size='13sp',
            bold=True
        )
        btn_cam.bind(on_press=self.open_camera)
        row_inputs.add_widget(btn_cam)

        btn_gallery = Button(
            text="🖼️ Gallery",
            background_normal='',
            background_color=(0.25, 0.30, 0.45, 1.0),
            font_size='13sp',
            bold=True
        )
        btn_gallery.bind(on_press=self.open_gallery)
        row_inputs.add_widget(btn_gallery)
        
        actions.add_widget(row_inputs)

        # Row 2: Export to Excel
        btn_export = Button(
            text="📥 Export to Excel (.xlsx)",
            size_hint=(1, None),
            height=dp(48),
            background_normal='',
            background_color=(0.06, 0.72, 0.50, 1.0),
            font_size='14sp',
            bold=True
        )
        btn_export.bind(on_press=self.export_to_excel)
        actions.add_widget(btn_export)

        root.add_widget(actions)
        return root

    def _update_bg(self, instance, value):
        self.bg_rect.size = instance.size
        self.bg_rect.pos = instance.pos

    def request_android_permissions(self):
        """Requests runtime permissions on Android."""
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.CAMERA,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE
            ])
        except Exception as e:
            print(f"[!] Android permissions: {e}")

    def get_app_storage_dir(self):
        """Returns writable directory on Android or Laptop."""
        if platform == 'android':
            from android.storage import app_storage_path
            try:
                p = app_storage_path()
                if p and os.path.exists(p):
                    return p
            except Exception:
                pass
        return os.path.dirname(os.path.abspath(__file__))

    def open_camera(self, instance=None):
        """Launches native camera on Android or opens file chooser fallback."""
        self.status_label.text = "Opening camera..."
        try:
            from plyer import camera
            save_name = f"aadhaar_snap_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            target_path = os.path.join(self.get_app_storage_dir(), save_name)
            camera.take_picture(filename=target_path, on_complete=self.on_camera_complete)
        except Exception as e:
            self.status_label.text = f"Native camera: {e}"
            self.fallback_file_chooser()

    def on_camera_complete(self, filepath):
        if filepath and os.path.exists(filepath):
            Clock.schedule_once(lambda dt: self.process_image_path(filepath), 0.2)
        else:
            self.status_label.text = "Camera photo not captured."

    def open_gallery(self, instance=None):
        """Opens native phone gallery / image picker."""
        self.status_label.text = "Opening gallery..."
        try:
            from plyer import filechooser
            filechooser.open_file(
                on_selection=self.on_gallery_complete,
                filters=[("Images", "*.jpg", "*.png", "*.jpeg", "*.webp")]
            )
        except Exception as e:
            self.status_label.text = f"Gallery picker: {e}"
            self.fallback_file_chooser()

    def on_gallery_complete(self, selection):
        if selection and len(selection) > 0:
            chosen = selection[0]
            Clock.schedule_once(lambda dt: self.process_image_path(chosen), 0.2)
        else:
            self.status_label.text = "No image selected."

    def fallback_file_chooser(self):
        """Fallback file browser dialog."""
        from kivy.uix.filechooser import FileChooserListView
        chooser = FileChooserListView(
            path=self.get_app_storage_dir(),
            filters=['*.png', '*.jpg', '*.jpeg', '*.webp']
        )
        
        popup_layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        popup_layout.add_widget(chooser)
        
        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        btn_select = Button(text="Select Image", background_color=(0.38, 0.40, 0.95, 1))
        btn_cancel = Button(text="Cancel", background_color=(0.3, 0.3, 0.3, 1))
        
        btn_row.add_widget(btn_select)
        btn_row.add_widget(btn_cancel)
        popup_layout.add_widget(btn_row)

        popup = Popup(title="Select Aadhaar Image", content=popup_layout, size_hint=(0.95, 0.9))
        
        def on_select(btn):
            if chooser.selection:
                selected_path = chooser.selection[0]
                popup.dismiss()
                self.process_image_path(selected_path)
        
        btn_select.bind(on_press=on_select)
        btn_cancel.bind(on_press=popup.dismiss)
        popup.open()

    def load_sample(self, instance=None):
        """Loads demo Aadhaar image immediately."""
        sample_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Screenshot 2026-10-28 133028.png")
        if not os.path.exists(sample_file):
            sample_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_aadhaar.png")
        
        self.process_image_path(sample_file)

    def process_image_path(self, path: str):
        """Displays image and executes offline OCR extraction."""
        if not os.path.exists(path):
            self.show_popup("Image Error", f"Cannot find image:\n{path}")
            return

        self.current_image_path = path
        self.img_preview.source = path
        self.status_label.text = "⚡ Scanning Aadhaar with Google ML Kit..."
        Clock.schedule_once(lambda dt: self._execute_ocr(path), 0.2)

    def _execute_ocr(self, path: str):
        lines: List[str] = []
        
        # 1. On Android: Run Google ML Kit Text Recognition on-device
        if platform == 'android':
            try:
                from jnius import autoclass
                BitmapFactory = autoclass('android.graphics.BitmapFactory')
                InputImage = autoclass('com.google.mlkit.vision.common.InputImage')
                TextRecognition = autoclass('com.google.mlkit.vision.text.TextRecognition')
                TextRecognizerOptions = autoclass('com.google.mlkit.vision.text.latin.TextRecognizerOptions')
                Tasks = autoclass('com.google.android.gms.tasks.Tasks')

                bitmap = BitmapFactory.decodeFile(path)
                if bitmap is not None:
                    input_image = InputImage.fromBitmap(bitmap, 0)
                    recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
                    # Use getattr to call Java 'await' method since await is a Python reserved keyword
                    await_fn = getattr(Tasks, 'await')
                    vision_text = await_fn(recognizer.process(input_image))
                    full_str = vision_text.getText()
                    lines = [ln.strip() for ln in full_str.split('\n') if ln.strip()]
            except Exception as e:
                print(f"[!] Google ML Kit recognition error: {e}")
        else:
            # 2. On Laptop/Desktop: Run EasyOCR if available, or fallback
            try:
                from aadhaar_ocr import AadhaarOCR
                ocr = AadhaarOCR(languages=['en', 'hi'], use_gpu=False, verbose=False)
                lines = ocr.extract_text(path)
            except Exception as e:
                print(f"[!] Desktop OCR note: {e}")

        # Parse extracted lines
        parsed = self.parse_aadhaar_text(lines)
        self.input_name.text = parsed.get('name') or ''
        self.input_aadhaar.text = parsed.get('aadhaar_number') or ''
        self.input_dob.text = parsed.get('dob') or ''
        self.input_gender.text = parsed.get('gender') or ''

        if parsed.get('aadhaar_number') or parsed.get('name'):
            self.status_label.text = "✓ OCR Complete! Fields extracted."
        else:
            self.status_label.text = "Image loaded. You can verify or edit fields below."

    def parse_aadhaar_text(self, lines: List[str]) -> Dict[str, Any]:
        """Offline Regex & Heuristic Parser for Aadhaar Card Fields."""
        full_text = " \n ".join(lines)
        data = {
            "aadhaar_number": "",
            "name": "",
            "dob": "",
            "gender": ""
        }

        # 1. Aadhaar Number (12 digits, often 4 4 4)
        aadhaar_pattern = r'\b(\d{4}\s\d{4}\s\d{4})\b|\b(\d{12})\b'
        matches = re.findall(aadhaar_pattern, full_text)
        if matches:
            m = matches[-1]
            num = m[0] if m[0] else m[1]
            if len(num) == 12:
                num = f"{num[:4]} {num[4:8]} {num[8:]}"
            data["aadhaar_number"] = num

        # 2. Date of Birth
        dob_patterns = [
            r'(?:DOB|D\.O\.B|Date\s*of\s*Birth|जन्म\s*तिथि|जन्म\s*तारीख)[\s:\-]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
            r'\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b',
            r'(?:Year\s*of\s*Birth|जन्म\s*वर्ष)[\s:\-]+(\d{4})\b'
        ]
        for pat in dob_patterns:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                data["dob"] = m.group(1).replace('-', '/').replace('.', '/')
                break

        # 3. Gender
        if re.search(r'\b(FEMALE|महिला)\b', full_text, re.IGNORECASE):
            data["gender"] = "FEMALE"
        elif re.search(r'\b(MALE|पुरुष)\b', full_text, re.IGNORECASE):
            data["gender"] = "MALE"
        elif re.search(r'\b(TRANSGENDER|उभयलिंगी)\b', full_text, re.IGNORECASE):
            data["gender"] = "TRANSGENDER"

        # 4. Name Heuristic
        ignore_words = [
            'government', 'india', 'bharat', 'sarkar', 'unique', 'identification',
            'authority', 'uidai', 'enrollment', 'help', 'dob', 'date', 'birth',
            'male', 'female', 'yob', 'year', 'address', 'card', 'aadhaar'
        ]
        candidate_name = None
        for i, line in enumerate(lines):
            if data["dob"] and data["dob"] in line:
                for back_i in range(i - 1, max(-1, i - 4), -1):
                    cand = lines[back_i].strip()
                    if not any(k in cand.lower() for k in ignore_words) and re.match(r'^[A-Za-z\s\.]{3,35}$', cand):
                        candidate_name = cand
                        break
                if candidate_name:
                    break

        if not candidate_name:
            for line in lines:
                cand = line.strip()
                if not any(k in cand.lower() for k in ignore_words) and re.match(r'^[A-Z][a-zA-Z\s\.]{2,30}$', cand):
                    candidate_name = cand
                    break

        data["name"] = candidate_name or ""
        return data

    def export_to_excel(self, instance=None):
        """Generates formatted .xlsx file directly on mobile storage."""
        aadhaar = self.input_aadhaar.text.strip()
        name = self.input_name.text.strip()
        dob = self.input_dob.text.strip()
        gender = self.input_gender.text.strip()

        if not aadhaar and not name:
            self.show_popup("Notice", "Please enter or scan Aadhaar card details first.")
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Aadhaar Card"

        headers = ["S.No.", "Aadhaar Number", "Full Name", "Date of Birth", "Gender", "Export Date"]
        ws.append(headers)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append([1, aadhaar, name, dob, gender, now_str])

        # Modern Indigo Header Styling
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        border_side = Side(border_style="thin", color="CBD5E1")
        border = Border(top=border_side, bottom=border_side, left=border_side, right=border_side)
        align_center = Alignment(horizontal="center", vertical="center")

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center
            cell.border = border

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=2, column=col_idx)
            cell.border = border
            if col_idx in [1, 2, 4, 5, 6]:
                cell.alignment = center_align

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = max(max_len + 4, 12)

        # Save to device storage (Downloads folder on Android)
        filename = f"Aadhaar_Data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        export_dir = self.get_app_storage_dir()
        if platform == 'android':
            try:
                from android.storage import primary_external_storage_path
                pub_dl = os.path.join(primary_external_storage_path(), "Download")
                if os.path.exists(pub_dl):
                    export_dir = pub_dl
            except Exception:
                pass

        export_path = os.path.join(export_dir, filename)
        wb.save(export_path)

        self.show_popup("Export Successful", f"Excel (.xlsx) file saved:\n\n{export_path}")

    def show_popup(self, title: str, message: str):
        layout = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(10))
        lbl = Label(text=message, font_size='13sp', halign='center')
        lbl.bind(size=lbl.setter('text_size'))
        layout.add_widget(lbl)
        
        btn_close = Button(
            text="OK",
            size_hint_y=None,
            height=dp(42),
            background_normal='',
            background_color=(0.38, 0.40, 0.95, 1),
            font_size='14sp',
            bold=True
        )
        layout.add_widget(btn_close)

        pop = Popup(title=title, content=layout, size_hint=(0.88, 0.42))
        btn_close.bind(on_press=pop.dismiss)
        pop.open()


if __name__ == '__main__':
    AadhaarMobileApp().run()
