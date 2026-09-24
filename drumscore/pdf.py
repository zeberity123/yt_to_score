import os
from pathlib import Path
import tempfile

from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


def title_font():
    if "ScoreTitle" in pdfmetrics.getRegisteredFontNames():
        return "ScoreTitle"
    fonts = [Path(os.environ.get("WINDIR", "C:/Windows"))/"Fonts"/name
             for name in ("malgun.ttf", "meiryo.ttc", "YuGothM.ttc")]
    fonts += [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for font in fonts:
        if font.exists():
            try:
                pdfmetrics.registerFont(TTFont("ScoreTitle", str(font)))
                return "ScoreTitle"
            except Exception:
                continue
    return "Helvetica"


def export_pdf(project, filename, paper="A4", gap_mm=1.5, margin_mm=12, title=None):
    included = [line for line in project.lines if line.included]
    if not included:
        raise ValueError("Select at least one score line to export.")
    if not 0 <= gap_mm <= 30 or not 5 <= margin_mm <= 40:
        raise ValueError("Gap must be 0–30 mm and margins 5–40 mm.")
    pagesize = {"A4": A4, "Letter": letter}[paper]
    width, height = pagesize
    margin, gap = margin_mm*72/25.4, gap_mm*72/25.4
    available_width = width-margin*2
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(suffix=".pdf", dir=filename.parent)
    os.close(fd)
    page = 1
    try:
        canvas = Canvas(temp, pagesize=pagesize)
        title = project.title if title is None else title
        canvas.setTitle(title)
        canvas.setAuthor("Drum Sheet Extractor")
        font = title_font()

        def header():
            canvas.setFont(font, 12)
            # Wrap long video titles instead of letting them run off the page.
            rows, row = [], ""
            for char in title:
                if pdfmetrics.stringWidth(row+char, font, 12) > available_width:
                    rows.append(row)
                    row = ""
                row += char
            if row:
                rows.append(row)
            for i, row in enumerate(rows[:3]):
                canvas.drawString(margin, height-margin-12-i*15, row)
            return height-margin-max(1, len(rows[:3]))*15-10

        def footer():
            canvas.setFont("Helvetica", 8)
            canvas.drawCentredString(width/2, margin*.55, str(page))

        y = header()
        for line in included:
            with Image.open(project.directory / line.path) as img:
                draw_width = available_width
                draw_height = img.height*draw_width/img.width
                if draw_height > height-margin*2-65:
                    factor = (height-margin*2-65)/draw_height
                    draw_width *= factor
                    draw_height *= factor
                if y-draw_height < margin:
                    footer()
                    canvas.showPage()
                    page += 1
                    y = height-margin
                canvas.drawImage(ImageReader(img), margin, y-draw_height,
                                 width=draw_width, height=draw_height)
                y -= draw_height+gap
        footer()
        canvas.save()
        os.replace(temp, filename)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return page
