import os
from pathlib import Path
import tempfile
from functools import lru_cache

from PIL import Image
from reportlab.lib.pagesizes import A3, A4, A5, B4, B5, LETTER, LEGAL, TABLOID
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from .print_layout import print_rows


PAPER_SIZES = {
    "A4": A4, "A3": A3, "A5": A5, "B4": B4, "B5": B5,
    "Letter": LETTER, "Legal": LEGAL, "Tabloid": TABLOID,
}


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


@lru_cache(maxsize=1)
def title_fallbacks():
    fonts = [title_font()]
    for index, name in enumerate(('meiryo.ttc', 'YuGothM.ttc')):
        path = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/name
        if path.exists():
            try:
                font = f'ScoreTitleFallback{index}'
                pdfmetrics.registerFont(TTFont(font, str(path)))
                fonts.append(font)
            except Exception:
                continue
    return fonts


def export_pdf(project, filename, paper="A4", gap_mm=0, margin_mm=12, title=None,
               *, left_margin_mm=3, right_margin_mm=3, bars_per_line=None,
               top_margin_mm=None, bottom_margin_mm=None, title_size=12, show_title=True, page_numbers=True):
    included = [line for line in project.lines if line.included]
    if not included:
        raise ValueError("Select at least one score line to export.")
    if not 0 <= gap_mm <= 30 or not 5 <= margin_mm <= 40:
        raise ValueError("Gap must be 0–30 mm and margins 5–40 mm.")
    left_margin_mm = margin_mm if left_margin_mm is None else left_margin_mm
    right_margin_mm = margin_mm if right_margin_mm is None else right_margin_mm
    if not 0 <= left_margin_mm <= 40 or not 0 <= right_margin_mm <= 40:
        raise ValueError("Left and right margins must be 0-40 mm.")
    top_margin_mm = margin_mm if top_margin_mm is None else top_margin_mm
    bottom_margin_mm = margin_mm if bottom_margin_mm is None else bottom_margin_mm
    if not 0 <= top_margin_mm <= 40 or not 0 <= bottom_margin_mm <= 40:
        raise ValueError("Top and bottom margins must be 0-40 mm.")
    if not 6 <= title_size <= 36:
        raise ValueError("Title size must be 6-36 pt.")
    if paper not in PAPER_SIZES:
        raise ValueError(f"Unsupported paper size: {paper}. Choose {', '.join(PAPER_SIZES)}.")
    pagesize = PAPER_SIZES[paper]
    width, height = pagesize
    gap = gap_mm*72/25.4
    top, bottom = top_margin_mm*72/25.4, bottom_margin_mm*72/25.4
    # A page number needs a little room under the last line, whatever the bottom margin.
    floor = max(bottom, 6*72/25.4) if page_numbers else bottom
    line_height = title_size*1.25
    left_margin, right_margin = left_margin_mm*72/25.4, right_margin_mm*72/25.4
    available_width = width-left_margin-right_margin
    rows, _ = print_rows(project,bars_per_line)
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(suffix=".pdf", dir=filename.parent)
    os.close(fd)
    page = 1
    try:
        canvas = Canvas(temp, pagesize=pagesize)
        title = project.title if title is None else title
        canvas.setTitle(title)
        canvas.setAuthor("Video Sheet to PDF")
        font = title_font()
        def character_font(char):
            if ord(char) < 128:
                return font
            for candidate in title_fallbacks():
                if ord(char) in getattr(pdfmetrics.getFont(candidate).face, 'charToGlyph', {}):
                    return candidate
            return font

        def header():
            if not show_title or not title.strip():
                return height-top
            canvas.setFont(font, title_size)
            # Wrap long video titles instead of letting them run off the page.
            rows, row, row_width = [], "", 0
            for char in title:
                char_width = pdfmetrics.stringWidth(char, character_font(char), title_size)
                if row_width+char_width > available_width:
                    rows.append(row)
                    row = ""
                    row_width = 0
                row += char
                row_width += char_width
            if row:
                rows.append(row)
            for i, row in enumerate(rows[:3]):
                text = canvas.beginText(left_margin, height-top-title_size-i*line_height)
                for char in row:
                    text.setFont(character_font(char), title_size)
                    text.textOut(char)
                canvas.drawText(text)
            return height-top-max(1, len(rows[:3]))*line_height-10

        def footer():
            if page_numbers:
                canvas.setFont("Helvetica", 8)
                canvas.drawCentredString(width/2, max(floor*.55, 4), str(page))

        y = header()
        reserve = height-y if show_title else 0  # title block on the first page
        for row in rows:
            with row.image as img:
                draw_width = available_width*row.width_fraction
                draw_height = img.height*draw_width/img.width*row.height_scale
                if draw_height > height-top-floor-reserve:
                    factor = (height-top-floor-reserve)/draw_height
                    draw_width *= factor
                    draw_height *= factor
                if y-draw_height < floor:
                    footer()
                    canvas.showPage()
                    page += 1
                    y = height-top
                canvas.drawImage(ImageReader(img), left_margin, y-draw_height,
                                 width=draw_width, height=draw_height)
                y -= draw_height+gap
        footer()
        canvas.save()
        os.replace(temp, filename)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return page
