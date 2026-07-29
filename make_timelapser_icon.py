from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "assets"
OUT.mkdir(parents=True, exist_ok=True)

size = 1024
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Background
bg = Image.new("RGBA", (size, size), (10, 12, 22, 255))
bg_draw = ImageDraw.Draw(bg)
for y in range(size):
    t = y / (size - 1)
    r = int(12 + (28 - 12) * t)
    g = int(14 + (18 - 14) * t)
    b = int(26 + (44 - 26) * t)
    bg_draw.line((0, y, size, y), fill=(r, g, b, 255))
img.alpha_composite(bg)

# Soft glow
for radius, alpha in ((260, 40), (180, 60), (110, 80)):
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((size*0.18, size*0.18, size*0.82, size*0.82), fill=(130, 165, 255, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(radius))
    img.alpha_composite(glow)

# Rounded frame
frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
fd = ImageDraw.Draw(frame)
margin = 70
fd.rounded_rectangle((margin, margin, size-margin, size-margin), radius=160, outline=(255, 255, 255, 235), width=16)
fd.rounded_rectangle((margin+18, margin+18, size-margin-18, size-margin-18), radius=142, outline=(255, 255, 255, 95), width=6)
img.alpha_composite(frame)

# Camera body
cam = Image.new("RGBA", (size, size), (0, 0, 0, 0))
cd = ImageDraw.Draw(cam)
cd.rounded_rectangle((300, 320, 760, 640), radius=38, fill=(245, 245, 248, 240), outline=(255, 255, 255, 245), width=10)
cd.rounded_rectangle((365, 270, 545, 360), radius=26, fill=(238, 238, 243, 240), outline=(255, 255, 255, 240), width=8)
cd.rounded_rectangle((340, 350, 420, 380), radius=8, fill=(245, 245, 248, 240))
cd.rounded_rectangle((610, 366, 690, 390), radius=8, fill=(245, 245, 248, 240))
img.alpha_composite(cam)

# Lens
lens = Image.new("RGBA", (size, size), (0, 0, 0, 0))
ld = ImageDraw.Draw(lens)
ld.ellipse((345, 372, 615, 642), outline=(255, 255, 255, 255), width=18)
ld.ellipse((378, 405, 582, 609), outline=(255, 255, 255, 255), width=12)
ld.ellipse((430, 455, 530, 555), fill=(16, 18, 28, 255))
ld.line((480, 470, 480, 410), fill=(255, 255, 255, 255), width=16)
ld.line((480, 480, 540, 520), fill=(255, 255, 255, 255), width=16)
img.alpha_composite(lens)

# Speed lines
speed = Image.new("RGBA", (size, size), (0, 0, 0, 0))
sd = ImageDraw.Draw(speed)
for y in (435, 482, 530, 585):
    sd.rounded_rectangle((210, y, 355, y+14), radius=7, fill=(255, 255, 255, 235))
sd.rounded_rectangle((245, 392, 290, 406), radius=6, fill=(255, 255, 255, 235))
img.alpha_composite(speed)

# Bottom label
try:
    font = ImageFont.truetype(str(OUT / "InterDisplay-Bold.woff2"), 92)
except Exception:
    font = ImageFont.load_default()
label = Image.new("RGBA", (size, size), (0, 0, 0, 0))
ld2 = ImageDraw.Draw(label)
text = "TIMELAPSER"
box = ld2.textbbox((0, 0), text, font=font)
text_x = (size - (box[2] - box[0])) // 2
text_y = 710
ld2.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(10, 10, 12, 255))
img.alpha_composite(label)

# Decorative line
line = Image.new("RGBA", (size, size), (0, 0, 0, 0))
lid = ImageDraw.Draw(line)
lid.line((250, 835, 390, 835), fill=(255, 255, 255, 235), width=12)
lid.line((634, 835, 774, 835), fill=(255, 255, 255, 235), width=12)
lid.ellipse((475, 810, 549, 884), fill=(255, 255, 255, 255))
img.alpha_composite(line)

ico = img.resize((256, 256), Image.LANCZOS)
ico.save(OUT / "timelapser.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
img.save(OUT / "timelapser.png")
print("Wrote assets/timelapser.ico and assets/timelapser.png")