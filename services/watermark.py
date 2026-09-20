import io
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

WATERMARK_TEXT = "PREVIEW — NOT FINAL"

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _get_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _make_overlay(width: int, height: int) -> Image.Image:
    """Tiled diagonal watermark overlay, returned as a transparent RGBA Image."""
    font_size = max(20, min(width, height) // 10)
    font = _get_font(font_size)

    diagonal = int(math.sqrt(width * width + height * height)) + font_size * 4
    canvas = Image.new("RGBA", (diagonal, diagonal), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    for y in range(0, diagonal, th + 80):
        for x in range(0, diagonal, tw + 60):
            draw.text((x, y), WATERMARK_TEXT, font=font, fill=(150, 150, 150, 110))

    canvas = canvas.rotate(30, resample=Image.Resampling.BICUBIC)

    ox = (diagonal - width) // 2
    oy = (diagonal - height) // 2
    return canvas.crop((ox, oy, ox + width, oy + height))


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

def _watermark_image(file_path: str) -> str:
    img = Image.open(file_path).convert("RGBA")
    w, h = img.size
    watermarked = Image.alpha_composite(img, _make_overlay(w, h))

    out_dir = Path(file_path).parent / "watermarked"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / (Path(file_path).stem + "_wm.png")
    watermarked.convert("RGB").save(str(out_path))
    return str(out_path)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _watermark_pdf(file_path: str) -> str:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.colors import Color
    from pypdf import PdfReader, PdfWriter
    import math

    reader = PdfReader(file_path)
    writer = PdfWriter()

    for page in reader.pages:
        pw = float(page.mediabox.width)
        ph = float(page.mediabox.height)

        packet = io.BytesIO()
        c = rl_canvas.Canvas(packet, pagesize=(pw, ph))
        font_size = max(10, int(min(pw, ph) / 18))
        c.setFont("Helvetica-Bold", font_size)
        c.setFillColor(Color(0.55, 0.55, 0.55, alpha=0.25))

        # Tile across the page at 30° — mirrors the image watermark logic.
        text_w = c.stringWidth(WATERMARK_TEXT, "Helvetica-Bold", font_size)
        col_gap = text_w + 40
        row_gap = font_size + 50
        diagonal = int(math.sqrt(pw * pw + ph * ph)) + font_size * 4

        c.saveState()
        c.translate(pw / 2, ph / 2)
        c.rotate(30)
        offset = diagonal // 2
        row = -offset
        while row < offset:
            col = -offset
            while col < offset:
                c.drawString(col, row, WATERMARK_TEXT)
                col += col_gap
            row += row_gap
        c.restoreState()
        c.save()

        packet.seek(0)
        wm_page = PdfReader(packet).pages[0]
        page.merge_page(wm_page)
        writer.add_page(page)

    out_dir = Path(file_path).parent / "watermarked"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / (Path(file_path).stem + "_wm.pdf")
    with open(out_path, "wb") as f:
        writer.write(f)
    return str(out_path)


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------

def _watermark_video(file_path: str) -> str:
    # Probe video dimensions so the overlay PNG matches exactly.
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            file_path,
        ],
        capture_output=True, text=True,
    )
    try:
        parts = probe.stdout.strip().split(",")
        w, h = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        w, h = 1920, 1080  # fallback if ffprobe can't read dimensions

    overlay_img = _make_overlay(w, h)
    tmp_overlay = Path(file_path).parent / f"_wm_tmp_{Path(file_path).stem}.png"
    overlay_img.save(str(tmp_overlay))

    out_dir = Path(file_path).parent / "watermarked"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / (Path(file_path).stem + "_wm.mp4")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", file_path,
                "-i", str(tmp_overlay),
                "-filter_complex", "[0:v][1:v]overlay=0:0",
                "-c:v", "libx264",
                "-c:a", "copy",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        tmp_overlay.unlink(missing_ok=True)

    return str(out_path)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_watermark(file_path: str, file_type: str) -> str:
    """
    Apply a diagonal 'PREVIEW — NOT FINAL' watermark and return the output path.
    Supports image/*, application/pdf, and video/*.
    Raises ValueError for unsupported types.
    """
    if file_type.startswith("image/"):
        return _watermark_image(file_path)
    if file_type == "application/pdf":
        return _watermark_pdf(file_path)
    if file_type.startswith("video/"):
        return _watermark_video(file_path)
    raise ValueError(f"Watermarking not supported for file type: {file_type}")
