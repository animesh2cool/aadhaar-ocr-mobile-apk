"""
Offline Aadhaar Card OCR Mobile Application
Built with Kivy for cross-platform desktop preview & Android deployment via Buildozer.
Features:
- Offline Aadhaar card scanning & parsing
- Smartphone aspect ratio window on laptop (390 x 780)
- Offline Excel (.xlsx) export using openpyxl
"""

import os
import sys
import datetime
from typing import Dict, Any, List

# Set mobile portrait dimensions when running on laptop/desktop
from kivy.config import Config
Config.set('graphics', 'width', '400')
Config.set('graphics', 'height', '800')
Config.set('graphics', 'resizable', '0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.clock import Clock
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Background styling
Window.clearcolor = (0.05, 0.07, 0.12, 1.0)


class AadhaarMobileApp(App):
    def build(self):
        self.title = "AadhaarScan Mobile (Offline)"
        self.records: List[Dict[str, str]] = []
        self.current_image_path = None
        self.ocr_engine = None

        # Root Layout
        root = BoxLayout(orientation='vertical', padding=12, spacing=10)

        # Header Bar
        header = BoxLayout(size_hint_y=None, height=50, spacing=8)
        header_title = Label(
            text="[b]AadhaarScan[/b] [color=6366f1]Offline[/color]",
            markup=True,
            font_size='18sp',
            halign='left',
            valign='middle'
        )
        header_title.bind(size=header_title.setter('text_size'))
        header.add_widget(header_title)

        sample_btn = Button(
            text="⚡ Test Sample",
            size_hint=(None, 1),
            width=115,
            background_normal='',
            background_color=(0.38, 0.40, 0.95, 0.8),
            font_size='12sp'
        )
        sample_btn.bind(on_press=self.load_sample)
        header.add_widget(sample_btn)
        root.add_widget(header)

        # Main Scrollable Content
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation='vertical', spacing=12, size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        # Card Preview Container
        self.img_preview = Image(
            source='',
            size_hint_y=None,
            height=200,
            allow_stretch=True,
            keep_ratio=True
        )
        content.add_widget(self.img_preview)

        # Scanner Status Banner
        self.status_label = Label(
            text="Ready. Tap 'Select Image' or 'Test Sample' to scan.",
            font_size='12sp',
            color=(0.6, 0.7, 0.8, 1),
            size_hint_y=None,
            height=28
        )
        content.add_widget(self.status_label)

        # Form Fields Box
        form = GridLayout(cols=1, spacing=8, size_hint_y=None)
        form.bind(minimum_height=form.setter('height'))

        # Name Field
        form.add_widget(Label(text="Full Name:", font_size='12sp', color=(0.8, 0.8, 0.9, 1), size_hint_y=None, height=20, halign='left'))
        self.input_name = TextInput(hint_text="e.g. RAHUL KUMAR", multiline=False, size_hint_y=None, height=38, background_color=(0.1, 0.14, 0.22, 1), foreground_color=(1, 1, 1, 1))
        form.add_widget(self.input_name)

        # Aadhaar Number Field
        form.add_widget(Label(text="Aadhaar Number (12 Digits):", font_size='12sp', color=(0.8, 0.8, 0.9, 1), size_hint_y=None, height=20, halign='left'))
        self.input_aadhaar = TextInput(hint_text="e.g. 0000 1111 2222", multiline=False, size_hint_y=None, height=38, background_color=(0.1, 0.14, 0.22, 1), foreground_color=(1, 0.5, 0.5, 1))
        form.add_widget(self.input_aadhaar)

        # DOB & Gender in 2 columns
        row_dob_gender = GridLayout(cols=2, spacing=10, size_hint_y=None, height=65)
        
        box_dob = BoxLayout(orientation='vertical', spacing=4)
        box_dob.add_widget(Label(text="Date of Birth:", font_size='12sp', color=(0.8, 0.8, 0.9, 1), size_hint_y=None, height=18))
        self.input_dob = TextInput(hint_text="DD/MM/YYYY", multiline=False, size_hint_y=None, height=38, background_color=(0.1, 0.14, 0.22, 1), foreground_color=(1, 1, 1, 1))
        box_dob.add_widget(self.input_dob)
        row_dob_gender.add_widget(box_dob)

        box_gender = BoxLayout(orientation='vertical', spacing=4)
        box_gender.add_widget(Label(text="Gender:", font_size='12sp', color=(0.8, 0.8, 0.9, 1), size_hint_y=None, height=18))
        self.input_gender = TextInput(hint_text="MALE / FEMALE", multiline=False, size_hint_y=None, height=38, background_color=(0.1, 0.14, 0.22, 1), foreground_color=(1, 1, 1, 1))
        box_gender.add_widget(self.input_gender)
        row_dob_gender.add_widget(box_gender)

        form.add_widget(row_dob_gender)
        content.add_widget(form)

        scroll.add_widget(content)
        root.add_widget(scroll)

        # Bottom Actions Bar
        actions = BoxLayout(orientation='vertical', spacing=8, size_hint_y=None, height=110)
        
        btn_scan = Button(
            text="📷 Select / Scan Card",
            size_hint=(1, None),
            height=46,
            background_normal='',
            background_color=(0.38, 0.40, 0.95, 1.0),
            font_size='14sp',
            bold=True
        )
        btn_scan.bind(on_press=self.open_file_selector)
        actions.add_widget(btn_scan)

        btn_export = Button(
            text="📥 Export to Excel (.xlsx)",
            size_hint=(1, None),
            height=46,
            background_normal='',
            background_color=(0.06, 0.72, 0.50, 1.0),
            font_size='14sp',
            bold=True
        )
        btn_export.bind(on_press=self.export_to_excel)
        actions.add_widget(btn_export)

        root.add_widget(actions)
        return root

    def load_sample(self, instance):
        """Loads the sample Aadhaar screenshot directly."""
        sample_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Screenshot 2026-10-28 133028.png")
        if not os.path.exists(sample_file):
            sample_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_aadhaar.png")
        
        self.process_image_path(sample_file)

    def open_file_selector(self, instance):
        """Opens a file dialog or camera capture."""
        from kivy.uix.filechooser import FileChooserListView
        chooser = FileChooserListView(
            path=os.path.dirname(os.path.abspath(__file__)),
            filters=['*.png', '*.jpg', '*.jpeg', '*.webp']
        )
        
        popup_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        popup_layout.add_widget(chooser)
        
        btn_row = BoxLayout(size_hint_y=None, height=44, spacing=10)
        btn_select = Button(text="Select Image", background_color=(0.38, 0.40, 0.95, 1))
        btn_cancel = Button(text="Cancel", background_color=(0.3, 0.3, 0.3, 1))
        
        btn_row.add_widget(btn_select)
        btn_row.add_widget(btn_cancel)
        popup_layout.add_widget(btn_row)

        popup = Popup(title="Choose Aadhaar Card Image", content=popup_layout, size_hint=(0.95, 0.9))
        
        def on_select(btn):
            if chooser.selection:
                selected_path = chooser.selection[0]
                popup.dismiss()
                self.process_image_path(selected_path)
        
        btn_select.bind(on_press=on_select)
        btn_cancel.bind(on_press=popup.dismiss)
        popup.open()

    def process_image_path(self, path: str):
        """Runs offline OCR on the image and populates fields."""
        if not os.path.exists(path):
            self.show_popup("Error", f"Image file not found: {path}")
            return

        self.current_image_path = path
        self.img_preview.source = path
        self.status_label.text = "⚡ Scanning card with offline OCR..."

        # Run OCR via scheduler to update UI
        Clock.schedule_once(lambda dt: self._run_ocr(path), 0.2)

    def _run_ocr(self, path: str):
        try:
            from aadhaar_ocr import AadhaarOCR
            if self.ocr_engine is None:
                self.ocr_engine = AadhaarOCR(languages=['en', 'hi'], use_gpu=False, verbose=False)
            
            result = self.ocr_engine.process_image(path)

            self.input_name.text = result.get('name') or ''
            self.input_aadhaar.text = result.get('aadhaar_number') or ''
            self.input_dob.text = result.get('dob') or ''
            self.input_gender.text = result.get('gender') or ''

            self.status_label.text = "✓ OCR Complete! Details extracted."
        except Exception as e:
            self.status_label.text = f"OCR Error: {e}"
            self.show_popup("OCR Notice", f"Error during OCR extraction:\n{e}")

    def export_to_excel(self, instance):
        """Exports the card details to an Excel file completely offline."""
        aadhaar = self.input_aadhaar.text.strip()
        name = self.input_name.text.strip()
        dob = self.input_dob.text.strip()
        gender = self.input_gender.text.strip()

        if not aadhaar and not name:
            self.show_popup("Empty Record", "Please scan or enter Aadhaar details before exporting.")
            return

        # Prepare Excel workbook using openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Aadhaar Card Data"

        # Headers
        headers = ["S.No.", "Aadhaar Number", "Full Name", "Date of Birth", "Gender", "Export Timestamp"]
        ws.append(headers)

        # Data row
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append([1, aadhaar, name, dob, gender, timestamp])

        # Style headers
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        border_side = Side(border_style="thin", color="CBD5E1")
        border = Border(top=border_side, bottom=border_side, left=border_side, right=border_side)
        center_align = Alignment(horizontal="center", vertical="center")

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = border

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=2, column=col_idx)
            cell.border = border
            if col_idx in [1, 2, 4, 5, 6]:
                cell.alignment = center_align

        # Auto-adjust column width
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = max(max_len + 4, 12)

        # Save to file
        file_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"Aadhaar_Data_{file_ts}.xlsx"
        export_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), export_filename)
        
        wb.save(export_path)
        self.show_popup("Export Successful", f"Offline Excel file generated successfully!\n\nSaved at:\n{export_path}")

    def show_popup(self, title: str, message: str):
        layout = BoxLayout(orientation='vertical', padding=14, spacing=10)
        lbl = Label(text=message, font_size='13sp', halign='center')
        lbl.bind(size=lbl.setter('text_size'))
        layout.add_widget(lbl)
        
        btn_close = Button(text="OK", size_hint_y=None, height=40, background_color=(0.38, 0.40, 0.95, 1))
        layout.add_widget(btn_close)

        pop = Popup(title=title, content=layout, size_hint=(0.85, 0.45))
        btn_close.bind(on_press=pop.dismiss)
        pop.open()


if __name__ == '__main__':
    AadhaarMobileApp().run()
