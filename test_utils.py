import os, tempfile
from aadhaar_utils import *

base = "23456789012"
good = base + verhoeff_check_digit(base)
assert verhoeff_valid(good) and is_valid_aadhaar(good), good
bad = good[:-1] + str((int(good[-1]) + 1) % 10)
assert not is_valid_aadhaar(bad)
print("valid sample:", format_aadhaar(good))

fg = format_aadhaar(good)
vid = "9123 4567 8901 2345"
lines = ["Government of India", "भारत सरकार", "Rahul Kumar", "DOB: 05/07/1990", "MALE",
         fg, "VID: " + vid, "Help: 1947"]
p = parse_aadhaar_text(lines)
print(p)
assert p == {"aadhaar_number": fg, "name": "Rahul Kumar", "dob": "05/07/1990", "gender": "MALE"}

# front + back appear twice, VID with no spaces, OCR confusion O->0
conf = fg.replace("0", "O")
p = parse_aadhaar_text(["Priya Sharma", "Year of Birth : 1995", "Female", conf, "1234567890123456"])
print(p)
assert p["aadhaar_number"] == fg and p["gender"] == "FEMALE" and p["dob"] == "1995" and p["name"] == "Priya Sharma"

# name above DOB, with junk above it
p = parse_aadhaar_text(["Aadhaar", "A B", "Anil Kumar Singh", "DOB 1/2/1980", "Male"])
print(p); assert p["name"] == "Anil Kumar Singh" and p["dob"] == "01/02/1980"

# empty
print(parse_aadhaar_text([]))

assert mask_aadhaar(fg) == "XXXX XXXX " + good[-4:]
assert format_aadhaar("2345678") == "2345 678"

d = tempfile.mkdtemp()
recs = [dict(aadhaar=fg, name="Rahul Kumar", dob="05/07/1990", gender="MALE", scanned_at="2026-10-30 10:00"),
        dict(aadhaar="1234 5678 9012", name="X", dob="", gender="", scanned_at="")]
out = export_records(recs, os.path.join(d, "t.xlsx"), mask=True)
import openpyxl
ws = openpyxl.load_workbook(out).active
for r in ws.iter_rows(values_only=True): print(r)

# image prep
from PIL import Image
im = Image.new("RGBA", (3000, 2000), (255, 255, 255, 255)); im.save(os.path.join(d, "a.png"))
o = prepare_image(os.path.join(d, "a.png"), d, rotate_deg=-90)
print(o, Image.open(o).size)
print("ALL OK")
