"""
Aadhaar Card OCR Reader using EasyOCR (Lightweight Deep Learning OCR)
Extracts:
 - Aadhaar Number (12 digits / XXXX XXXX XXXX)
 - Name
 - Date of Birth (DOB) or Year of Birth (YOB)
 - Gender (Male / Female / Transgender)
 - PIN Code & Care-of (C/O, S/O, D/O, W/O) if present
"""

import os
import sys
import re
import argparse
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import easyocr


class AadhaarOCR:
    def __init__(self, languages: Optional[List[str]] = None, use_gpu: bool = False, verbose: bool = False):
        """
        Initializes EasyOCR reader with lightweight English and Hindi models.
        """
        if languages is None:
            languages = ['en', 'hi']
        print(f"[*] Initializing EasyOCR model (languages={languages}, gpu={use_gpu})...")
        self.reader = easyocr.Reader(languages, gpu=use_gpu, verbose=verbose)

    def extract_text(self, image_path: str) -> List[str]:
        """Runs OCR on the given image path and returns detected text lines."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # EasyOCR returns list of (bbox, text, prob)
        results = self.reader.readtext(image_path)
        # Filter low confidence detections (< 0.25) and strip text
        extracted_lines = [res[1].strip() for res in results if res[2] > 0.25 and res[1].strip()]
        return extracted_lines

    @staticmethod
    def parse_aadhaar(lines: List[str]) -> Dict[str, Any]:
        """
        Parses raw OCR lines using pattern matching and heuristics
        to extract Aadhaar card fields.
        """
        data: Dict[str, Any] = {
            "aadhaar_number": None,
            "name": None,
            "dob": None,
            "gender": None,
            "relation_name": None,
            "pincode": None,
            "raw_text": lines
        }

        full_text = " \n ".join(lines)

        # 1. Aadhaar Number (12 digits, often 4 4 4)
        # Matches patterns like 1234 5678 9012 or 123456789012
        aadhaar_pattern = r'\b(\d{4}\s\d{4}\s\d{4})\b|\b(\d{12})\b'
        aadhaar_matches = re.findall(aadhaar_pattern, full_text)
        if aadhaar_matches:
            match = aadhaar_matches[-1] # Usually at the bottom
            num = match[0] if match[0] else match[1]
            if len(num) == 12:
                num = f"{num[:4]} {num[4:8]} {num[8:]}"
            data["aadhaar_number"] = num

        # 2. Date of Birth (DOB) / Year of Birth
        dob_patterns = [
            r'(?:DOB|D\.O\.B|Date\s*of\s*Birth|जन्म\s*तिथि|जन्म\s*तारीख)[\s:\-]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
            r'\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b',
            r'(?:Year\s*of\s*Birth|जन्म\s*वर्ष)[\s:\-]+(\d{4})\b'
        ]
        for pat in dob_patterns:
            dob_match = re.search(pat, full_text, re.IGNORECASE)
            if dob_match:
                data["dob"] = dob_match.group(1).replace('-', '/').replace('.', '/')
                break

        # 3. Gender
        gender_patterns = [
            (r'\b(FEMALE|महिला)\b', 'FEMALE'),
            (r'\b(MALE|पुरुष)\b', 'MALE'),
            (r'\b(TRANSGENDER|उभयलिंगी)\b', 'TRANSGENDER')
        ]
        for pat, g_val in gender_patterns:
            if re.search(pat, full_text, re.IGNORECASE):
                data["gender"] = g_val
                break

        # 4. PIN Code (6 digits, not part of 12 digit aadhaar)
        pin_matches = re.findall(r'\b([1-9][0-9]{5})\b', full_text)
        if pin_matches:
            # Avoid 6-digit substrings that might be part of an unspaced 12-digit number
            valid_pins = [p for p in pin_matches if data["aadhaar_number"] and p not in data["aadhaar_number"].replace(' ', '')]
            data["pincode"] = valid_pins[0] if valid_pins else pin_matches[0]

        # 5. Care-of / Relation (S/O, D/O, W/O, C/O)
        rel_pattern = r'(?:S/O|D/O|W/O|C/O|आत्मज|पुत्र|पुत्री|पत्नी)[\s:\-]+([A-Za-z\s]+)'
        rel_match = re.search(rel_pattern, full_text, re.IGNORECASE)
        if rel_match:
            data["relation_name"] = rel_match.group(1).strip()

        # 6. Name Heuristic
        # Usually appears after "Government of India" / "भारत सरकार" and before DOB
        ignore_keywords = [
            'government', 'india', 'bharat', 'sarkar', 'unique', 'identification',
            'authority', 'uidai', 'enrollment', 'help', 'dob', 'date', 'birth',
            'male', 'female', 'yob', 'year', 'address', 'card', 'aadhaar', 'father'
        ]

        candidate_name = None
        for i, line in enumerate(lines):
            line_clean = line.strip()
            # If line matches DOB, name is likely 1-2 lines above it
            if data["dob"] and data["dob"] in line:
                for back_idx in range(i - 1, max(-1, i - 4), -1):
                    cand = lines[back_idx].strip()
                    cand_lower = cand.lower()
                    if not any(k in cand_lower for k in ignore_keywords) and re.match(r'^[A-Za-z\s\.]{3,35}$', cand):
                        candidate_name = cand
                        break
                if candidate_name:
                    break

        # Fallback for name: find first clean title-cased English name line
        if not candidate_name:
            for line in lines:
                cand = line.strip()
                cand_lower = cand.lower()
                if not any(k in cand_lower for k in ignore_keywords):
                    if re.match(r'^[A-Z][a-zA-Z\s\.]{2,30}$', cand):
                        candidate_name = cand
                        break

        data["name"] = candidate_name

        return data

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """Runs OCR and parsing on the image."""
        lines = self.extract_text(image_path)
        parsed = self.parse_aadhaar(lines)
        return parsed


def create_demo_aadhaar_card(output_path: str = "sample_aadhaar.png"):
    """
    Creates a synthetic sample Aadhaar card image to test the OCR immediately.
    """
    width, height = 800, 500
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Card border
    draw.rounded_rectangle([15, 15, width - 15, height - 15], radius=15, outline=(180, 180, 180), width=3)
    
    # Top banner / Header
    draw.rectangle([20, 20, width - 20, 90], fill=(245, 245, 250))
    
    # Default PIL font
    try:
        font_large = ImageFont.truetype("arial.ttf", 26)
        font_medium = ImageFont.truetype("arial.ttf", 20)
        font_bold = ImageFont.truetype("arialbd.ttf", 24)
        font_aadhaar = ImageFont.truetype("arialbd.ttf", 34)
    except Exception:
        font_large = font_medium = font_bold = font_aadhaar = ImageFont.load_default()

    draw.text((width // 2 - 130, 30), "Government of India", fill=(20, 20, 20), font=font_large)
    draw.text((width // 2 - 100, 60), "भारत सरकार", fill=(60, 60, 60), font=font_medium)

    # Photo placeholder box
    draw.rectangle([50, 120, 200, 300], fill=(225, 230, 240), outline=(150, 150, 150), width=2)
    draw.text((80, 200), "[ PHOTO ]", fill=(100, 100, 100), font=font_medium)

    # Demographic details
    draw.text((240, 130), "Kalim Khan", fill=(0, 0, 0), font=font_bold)
    draw.text((240, 165), "कलीम खान", fill=(60, 60, 60), font=font_medium)
    draw.text((240, 210), "DOB: 15/08/1995", fill=(0, 0, 0), font=font_medium)
    draw.text((240, 250), "Gender / लिंग: MALE", fill=(0, 0, 0), font=font_medium)

    # Aadhaar Number at bottom
    draw.rectangle([50, 380, width - 50, 460], fill=(248, 249, 250))
    draw.text((width // 2 - 160, 400), "5482 9104 3627", fill=(180, 0, 0), font=font_aadhaar)

    img.save(output_path)
    print(f"[+] Generated sample Aadhaar card image at: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Aadhaar Card OCR Reader using EasyOCR")
    parser.add_argument("image", nargs="?", default=None, help="Path to Aadhaar card image")
    parser.add_argument("--demo", action="store_true", help="Generate a sample Aadhaar card and run OCR on it")
    parser.add_argument("--gpu", action="store_true", help="Use GPU acceleration if available")
    args = parser.parse_args()

    image_path = args.image
    if not image_path or args.demo:
        demo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_aadhaar.png")
        create_demo_aadhaar_card(demo_path)
        image_path = demo_path

    ocr = AadhaarOCR(languages=['en', 'hi'], use_gpu=args.gpu)
    print(f"\n[+] Processing image: {image_path}")
    result = ocr.process_image(image_path)

    print("\n" + "=" * 50)
    print("        AADHAAR CARD OCR RESULTS")
    print("=" * 50)
    print(f" Name           : {result['name']}")
    print(f" Aadhaar Number : {result['aadhaar_number']}")
    print(f" Date of Birth  : {result['dob']}")
    print(f" Gender         : {result['gender']}")
    if result['relation_name']:
        print(f" C/O or S/O     : {result['relation_name']}")
    if result['pincode']:
        print(f" PIN Code       : {result['pincode']}")
    print("=" * 50)

    print("\n[+] Raw Detected Lines:")
    for i, line in enumerate(result['raw_text'], 1):
        print(f"  {i:02d}. {line}")


if __name__ == "__main__":
    main()
