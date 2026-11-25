"""
Generates 9 polished, modern illustrations for System Architecture Pipeline rows.
Outputs to ui/src/assets/pipeline/rows/ and ui/public/pipeline/rows/
"""
import os
import shutil
from PIL import Image, ImageDraw, ImageFont

SIZE = 256  # 4x supersampling for 32-36px display

def create_base():
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

def finalize(img, filename):
    out1 = os.path.join("ui/src/assets/pipeline/rows", filename)
    out2 = os.path.join("ui/public/pipeline/rows", filename)
    img.save(out1, "PNG")
    shutil.copyfile(out1, out2)
    print(f"Generated {filename}")

# 1. Meter readings (Electric digital meter)
def gen_meter_readings():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([36, 44, 220, 228], radius=28, fill=(0, 0, 0, 35))
    
    # Meter housing (Blue gradient look)
    d.rounded_rectangle([32, 36, 216, 220], radius=28, fill=(30, 64, 175, 255), outline=(59, 130, 246, 255), width=6)
    d.rounded_rectangle([42, 46, 206, 210], radius=22, fill=(37, 99, 235, 255))
    
    # Digital LCD display screen
    d.rounded_rectangle([56, 68, 192, 136], radius=14, fill=(15, 23, 42, 255), outline=(148, 163, 184, 255), width=4)
    # LCD glowing readout lines (simulating digital numbers)
    d.rectangle([68, 88, 76, 116], fill=(56, 189, 248, 255))
    d.rectangle([84, 88, 108, 94], fill=(56, 189, 248, 255))
    d.rectangle([84, 110, 108, 116], fill=(56, 189, 248, 255))
    d.rectangle([102, 88, 108, 116], fill=(56, 189, 248, 255))
    d.rectangle([116, 88, 140, 94], fill=(56, 189, 248, 255))
    d.rectangle([116, 99, 140, 105], fill=(56, 189, 248, 255))
    d.rectangle([116, 110, 140, 116], fill=(56, 189, 248, 255))
    d.rectangle([134, 88, 140, 116], fill=(56, 189, 248, 255))
    # "kWh" indicator text dot
    d.ellipse([148, 110, 154, 116], fill=(56, 189, 248, 255))
    d.rectangle([160, 92, 180, 100], fill=(56, 189, 248, 220))
    
    # Status LED indicators
    d.ellipse([64, 154, 80, 170], fill=(34, 197, 94, 255), outline=(22, 101, 52, 255), width=2) # Green LED
    d.ellipse([92, 154, 108, 170], fill=(245, 158, 11, 255), outline=(180, 83, 9, 255), width=2) # Amber LED
    d.ellipse([120, 154, 136, 170], fill=(239, 68, 68, 255), outline=(153, 27, 27, 255), width=2) # Red LED
    
    # Lightning bolt badge on bottom right
    d.ellipse([156, 150, 212, 206], fill=(245, 158, 11, 255), outline=(255, 255, 255, 255), width=4)
    bolt = [(186, 158), (170, 178), (184, 178), (178, 198), (198, 174), (184, 174)]
    d.polygon(bolt, fill=(255, 255, 255, 255))
    
    finalize(im, "meter-readings.png")

# 2. Production logs (Spreadsheet clipboard / production board)
def gen_production_logs():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([44, 38, 212, 228], radius=20, fill=(0, 0, 0, 35))
    
    # Document Body (Green themed Excel / production sheet)
    d.rounded_rectangle([40, 30, 208, 220], radius=20, fill=(255, 255, 255, 255), outline=(22, 163, 74, 255), width=6)
    
    # Green header banner
    d.rounded_rectangle([40, 30, 208, 80], radius=20, fill=(22, 163, 74, 255))
    d.rectangle([40, 60, 208, 80], fill=(22, 163, 74, 255))
    
    # Spreadsheet grid icon on header
    d.rectangle([60, 44, 94, 68], fill=(255, 255, 255, 255))
    d.line([(60, 56), (94, 56)], fill=(22, 163, 74, 255), width=3)
    d.line([(77, 44), (77, 68)], fill=(22, 163, 74, 255), width=3)
    
    # Header title bars
    d.rounded_rectangle([108, 48, 188, 56], radius=4, fill=(240, 253, 244, 255))
    d.rounded_rectangle([108, 62, 164, 68], radius=3, fill=(220, 252, 231, 255))
    
    # Table rows inside sheet
    row_y = [96, 126, 156]
    for y in row_y:
        d.rounded_rectangle([56, y, 192, y + 20], radius=6, fill=(240, 253, 244, 255), outline=(187, 247, 208, 255), width=2)
        d.ellipse([64, y + 5, 74, y + 15], fill=(34, 197, 94, 255)) # Green check dot
        d.rectangle([84, y + 7, 134, y + 13], fill=(100, 116, 139, 255))
        d.rectangle([146, y + 7, 182, y + 13], fill=(34, 197, 94, 255))
        
    # Production bar chart badge on bottom right
    d.rounded_rectangle([140, 160, 216, 224], radius=14, fill=(21, 128, 61, 255), outline=(255, 255, 255, 255), width=4)
    d.rectangle([152, 198, 162, 214], fill=(255, 255, 255, 255))
    d.rectangle([168, 184, 178, 214], fill=(255, 255, 255, 255))
    d.rectangle([184, 172, 194, 214], fill=(255, 255, 255, 255))
    d.rectangle([200, 188, 206, 214], fill=(255, 255, 255, 255))
    
    finalize(im, "production-logs.png")

# 3. Operating context (Shift calendar & schedule)
def gen_operating_context():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([44, 42, 212, 226], radius=20, fill=(0, 0, 0, 35))
    
    # Calendar body
    d.rounded_rectangle([40, 36, 208, 220], radius=20, fill=(255, 255, 255, 255), outline=(109, 40, 217, 255), width=6)
    
    # Purple Header
    d.rounded_rectangle([40, 36, 208, 86], radius=20, fill=(109, 40, 217, 255))
    d.rectangle([40, 64, 208, 86], fill=(109, 40, 217, 255))
    
    # Binder rings
    for rx in [70, 104, 144, 178]:
        d.rounded_rectangle([rx - 6, 24, rx + 6, 48], radius=6, fill=(148, 163, 184, 255), outline=(71, 85, 105, 255), width=2)
        d.ellipse([rx - 4, 32, rx + 4, 40], fill=(255, 255, 255, 255))
        
    # Month / Context text line
    d.rounded_rectangle([80, 58, 168, 68], radius=4, fill=(245, 243, 255, 255))
    
    # Calendar grid
    for row in range(3):
        for col in range(4):
            gx = 60 + col * 34
            gy = 104 + row * 26
            if row == 1 and col == 2:
                d.rounded_rectangle([gx, gy, gx + 24, gy + 18], radius=4, fill=(168, 85, 247, 255)) # Selected shift day
            else:
                d.rounded_rectangle([gx, gy, gx + 24, gy + 18], radius=4, fill=(245, 243, 255, 255))
                
    # Clock badge on bottom right
    d.ellipse([144, 144, 216, 216], fill=(124, 58, 237, 255), outline=(255, 255, 255, 255), width=4)
    d.ellipse([152, 152, 208, 208], fill=(255, 255, 255, 255))
    # Clock hands
    d.line([(180, 180), (180, 162)], fill=(124, 58, 237, 255), width=5) # Hour hand
    d.line([(180, 180), (196, 180)], fill=(124, 58, 237, 255), width=4) # Minute hand
    d.ellipse([176, 176, 184, 184], fill=(124, 58, 237, 255))
    
    finalize(im, "operating-context.png")

# 4. Match plant hours (Clock + Power Meter synchronization)
def gen_match_plant_hours():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.ellipse([38, 38, 218, 218], fill=(0, 0, 0, 35))
    
    # Clock Outer Dial
    d.ellipse([32, 32, 214, 214], fill=(107, 33, 168, 255), outline=(168, 85, 247, 255), width=6)
    d.ellipse([46, 46, 200, 200], fill=(250, 245, 255, 255), outline=(192, 132, 252, 255), width=4)
    
    # Clock tick marks
    d.rectangle([120, 52, 126, 64], fill=(107, 33, 168, 255))
    d.rectangle([120, 182, 126, 194], fill=(107, 33, 168, 255))
    d.rectangle([52, 120, 64, 126], fill=(107, 33, 168, 255))
    d.rectangle([182, 120, 194, 126], fill=(107, 33, 168, 255))
    
    # Circular telemetry matching wave
    d.arc([68, 68, 178, 178], start=210, end=380, fill=(168, 85, 247, 255), width=6)
    
    # Clock hands
    d.line([(123, 123), (123, 76)], fill=(107, 33, 168, 255), width=6)
    d.line([(123, 123), (160, 123)], fill=(147, 51, 234, 255), width=5)
    d.ellipse([117, 117, 129, 129], fill=(107, 33, 168, 255))
    
    # Sync gear badge on bottom right
    d.ellipse([144, 144, 216, 216], fill=(147, 51, 234, 255), outline=(255, 255, 255, 255), width=4)
    # Small meter pulse icon inside badge
    d.line([(156, 180), (168, 180), (176, 164), (184, 194), (192, 174), (204, 174)], fill=(255, 255, 255, 255), width=4)
    
    finalize(im, "match-plant-hours.png")

# 5. Calculate unit cost (Cost sheet & calculator with currency)
def gen_calculate_unit_cost():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([42, 38, 214, 226], radius=24, fill=(0, 0, 0, 35))
    
    # Calculator / Cost sheet Body
    d.rounded_rectangle([36, 32, 210, 220], radius=24, fill=(14, 116, 144, 255), outline=(6, 182, 212, 255), width=6)
    d.rounded_rectangle([46, 42, 200, 210], radius=18, fill=(236, 254, 255, 255))
    
    # Display screen with cost calculation
    d.rounded_rectangle([58, 54, 188, 102], radius=10, fill=(15, 23, 42, 255), outline=(14, 116, 144, 255), width=3)
    # Digital numbers & formula (Cost ÷ Good units)
    d.rectangle([70, 72, 108, 80], fill=(103, 232, 249, 255))
    d.rectangle([116, 74, 132, 78], fill=(103, 232, 249, 255)) # Division symbol
    d.ellipse([122, 68, 126, 72], fill=(103, 232, 249, 255))
    d.ellipse([122, 80, 126, 84], fill=(103, 232, 249, 255))
    d.rectangle([140, 68, 176, 88], fill=(103, 232, 249, 255))
    
    # Keypad grid
    for r in range(3):
        for c in range(3):
            bx = 64 + c * 42
            by = 116 + r * 28
            d.rounded_rectangle([bx, by, bx + 32, by + 20], radius=6, fill=(207, 250, 254, 255), outline=(14, 116, 144, 255), width=2)
            d.rectangle([bx + 8, by + 8, bx + 24, by + 12], fill=(14, 116, 144, 255))
            
    # Currency symbol badge on bottom right (₹ Rupee symbol)
    d.ellipse([144, 144, 216, 216], fill=(8, 145, 178, 255), outline=(255, 255, 255, 255), width=4)
    # Draw ₹ Rupee
    d.line([(164, 164), (196, 164)], fill=(255, 255, 255, 255), width=4)
    d.line([(164, 172), (196, 172)], fill=(255, 255, 255, 255), width=4)
    d.line([(174, 164), (174, 186)], fill=(255, 255, 255, 255), width=4)
    d.arc([164, 166, 192, 192], start=270, end=90, fill=(255, 255, 255, 255), width=4)
    d.line([(174, 186), (194, 204)], fill=(255, 255, 255, 255), width=4)
    
    finalize(im, "calculate-unit-cost.png")

# 6. Flag unusual use (Anomaly trend line with alert spike)
def gen_flag_unusual_use():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([40, 42, 216, 226], radius=24, fill=(0, 0, 0, 35))
    
    # Chart screen body
    d.rounded_rectangle([34, 36, 212, 220], radius=24, fill=(180, 83, 9, 255), outline=(245, 158, 11, 255), width=6)
    d.rounded_rectangle([44, 46, 202, 210], radius=18, fill=(254, 243, 199, 255))
    
    # Grid lines
    d.line([(60, 68), (186, 68)], fill=(253, 230, 138, 255), width=2)
    d.line([(60, 108), (186, 108)], fill=(253, 230, 138, 255), width=2)
    d.line([(60, 148), (186, 148)], fill=(253, 230, 138, 255), width=2)
    d.line([(60, 188), (186, 188)], fill=(217, 119, 6, 255), width=3) # Baseline
    d.line([(60, 68), (60, 188)], fill=(217, 119, 6, 255), width=3)   # Y-axis
    
    # Trend line with sharp unusual spike
    trend_pts = [
        (64, 154),
        (84, 148),
        (104, 156),
        (124, 72),  # Spike!
        (144, 142),
        (164, 138),
        (184, 144)
    ]
    d.line(trend_pts, fill=(217, 119, 6, 255), width=6)
    
    # Area under curve
    d.polygon(trend_pts + [(184, 186), (64, 186)], fill=(254, 215, 170, 140))
    
    # Alert pulse indicator at the peak (124, 72)
    d.ellipse([110, 58, 138, 86], fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=4)
    # Exclamation mark inside alert badge
    d.line([(124, 65), (124, 75)], fill=(255, 255, 255, 255), width=3)
    d.ellipse([122, 78, 126, 82], fill=(255, 255, 255, 255))
    
    # Warning badge on bottom right
    d.ellipse([144, 144, 216, 216], fill=(245, 158, 11, 255), outline=(255, 255, 255, 255), width=4)
    # Warning triangle
    tri = [(180, 156), (158, 198), (202, 198)]
    d.polygon(tri, fill=(255, 255, 255, 255))
    d.line([(180, 168), (180, 184)], fill=(245, 158, 11, 255), width=3)
    d.ellipse([178, 188, 182, 192], fill=(245, 158, 11, 255))
    
    finalize(im, "flag-unusual-use.png")

# 7. Compare periods (Before & After comparison bar chart)
def gen_compare_periods():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([42, 40, 216, 224], radius=24, fill=(0, 0, 0, 35))
    
    # Card Body
    d.rounded_rectangle([36, 34, 212, 218], radius=24, fill=(180, 83, 9, 255), outline=(245, 158, 11, 255), width=6)
    d.rounded_rectangle([46, 44, 202, 208], radius=18, fill=(255, 251, 235, 255))
    
    # Ground baseline
    d.line([(56, 174), (192, 174)], fill=(180, 83, 9, 255), width=4)
    
    # Group 1: Baseline vs Post
    # Baseline bar (higher)
    d.rounded_rectangle([66, 80, 94, 174], radius=6, fill=(217, 119, 6, 255))
    # Post bar (lower - verified drop)
    d.rounded_rectangle([102, 116, 130, 174], radius=6, fill=(16, 185, 129, 255))
    
    # Group 2: Next period
    d.rounded_rectangle([142, 92, 170, 174], radius=6, fill=(245, 158, 11, 255))
    
    # Comparison delta arrow (showing decrease)
    d.line([(80, 64), (116, 64)], fill=(16, 185, 129, 255), width=4)
    d.line([(116, 64), (116, 104)], fill=(16, 185, 129, 255), width=4)
    d.polygon([(110, 100), (122, 100), (116, 110)], fill=(16, 185, 129, 255))
    
    # Comparison columns badge on bottom right
    d.ellipse([144, 144, 216, 216], fill=(217, 119, 6, 255), outline=(255, 255, 255, 255), width=4)
    d.rectangle([160, 162, 174, 198], fill=(255, 255, 255, 255))
    d.rectangle([182, 172, 196, 198], fill=(255, 255, 255, 255))
    
    finalize(im, "compare-periods.png")

# 8. Check output (4 production guardrails verified checklist)
def gen_check_output():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([44, 40, 212, 226], radius=22, fill=(0, 0, 0, 35))
    
    # Clipboard Body
    d.rounded_rectangle([40, 34, 208, 220], radius=22, fill=(22, 163, 74, 255), outline=(34, 197, 94, 255), width=6)
    d.rounded_rectangle([48, 42, 200, 212], radius=16, fill=(240, 253, 244, 255))
    
    # Top clip
    d.rounded_rectangle([92, 24, 156, 48], radius=8, fill=(71, 85, 105, 255), outline=(30, 41, 59, 255), width=3)
    d.ellipse([118, 30, 130, 42], fill=(240, 253, 244, 255))
    
    # 3 verified checklist rows
    for i, y in enumerate([72, 106, 140]):
        # Green check circle
        d.ellipse([62, y, 86, y + 24], fill=(34, 197, 94, 255))
        # White checkmark
        d.line([(68, y + 12), (73, y + 18), (81, y + 7)], fill=(255, 255, 255, 255), width=3)
        # Text line
        d.rounded_rectangle([96, y + 6, 184, y + 18], radius=4, fill=(187, 247, 208, 255))
        
    # Big Verified Stamp Badge on bottom right
    d.ellipse([140, 140, 218, 218], fill=(22, 163, 74, 255), outline=(255, 255, 255, 255), width=5)
    d.line([(158, 178), (172, 194), (198, 160)], fill=(255, 255, 255, 255), width=7)
    
    finalize(im, "check-output.png")

# 9. Assess savings (Savings report with gold award / seal)
def gen_assess_savings():
    im = create_base()
    d = ImageDraw.Draw(im)
    
    # Shadow
    d.rounded_rectangle([44, 38, 212, 226], radius=20, fill=(0, 0, 0, 35))
    
    # Certificate / Savings Report Document
    d.rounded_rectangle([40, 30, 208, 220], radius=20, fill=(255, 255, 255, 255), outline=(159, 18, 57, 255), width=6)
    
    # Burgundy Header
    d.rounded_rectangle([40, 30, 208, 76], radius=20, fill=(159, 18, 57, 255))
    d.rectangle([40, 56, 208, 76], fill=(159, 18, 57, 255))
    
    # Header gold bar
    d.rounded_rectangle([80, 46, 168, 56], radius=4, fill=(254, 205, 211, 255))
    
    # Report text lines
    d.rounded_rectangle([58, 92, 178, 100], radius=4, fill=(244, 63, 94, 255))
    d.rounded_rectangle([58, 110, 154, 118], radius=4, fill=(226, 232, 240, 255))
    d.rounded_rectangle([58, 128, 140, 136], radius=4, fill=(226, 232, 240, 255))
    d.rounded_rectangle([58, 146, 128, 154], radius=4, fill=(226, 232, 240, 255))
    
    # Upward green savings trend arrow on left
    d.line([(70, 194), (96, 168)], fill=(16, 185, 129, 255), width=6)
    d.polygon([(90, 164), (104, 164), (104, 178)], fill=(16, 185, 129, 255))
    
    # Gold Rosette Medal / Savings Ribbon Badge on bottom right
    # Ribbon tails
    d.polygon([(160, 194), (168, 224), (178, 206)], fill=(217, 119, 6, 255))
    d.polygon([(194, 194), (188, 224), (178, 206)], fill=(217, 119, 6, 255))
    # Medal circle
    d.ellipse([144, 144, 214, 214], fill=(245, 158, 11, 255), outline=(255, 255, 255, 255), width=4)
    d.ellipse([156, 156, 202, 202], fill=(251, 191, 36, 255))
    # Star / Award symbol inside medal
    d.polygon([
        (179, 164), (183, 174), (194, 174), (185, 180),
        (188, 190), (179, 184), (170, 190), (173, 180),
        (164, 174), (175, 174)
    ], fill=(180, 83, 9, 255))
    
    finalize(im, "assess-savings.png")

if __name__ == "__main__":
    gen_meter_readings()
    gen_production_logs()
    gen_operating_context()
    gen_match_plant_hours()
    gen_calculate_unit_cost()
    gen_flag_unusual_use()
    gen_compare_periods()
    gen_check_output()
    gen_assess_savings()
    print("All 9 pipeline row illustrations generated successfully!")
