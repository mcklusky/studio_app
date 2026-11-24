"""Customer receipt as a branded PDF, 76 mm wide (fits thermal paper; shares well on WhatsApp).

Rendered from SaleDetailSerializer data so the PDF, the on-screen receipt and the API
always agree. Costs and profit are never included, whoever asks.
"""

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.common import brand

WIDTH_MM = 76
THANKS = "Thank you for choosing Just Smile Empire."


def _t(value):
    # Built-in PDF fonts are Latin-1: swap typographic characters they cannot draw.
    text = "" if value is None else str(value)
    for a, b in (("−", "-"), ("—", "-"), ("–", "-"), ("×", "x"), ("’", "'")):
        text = text.replace(a, b)
    return escape(text.encode("latin-1", "replace").decode("latin-1"))


def money(value, currency):
    return f"{currency} {Decimal(value):,.2f}"


def quantity(value):
    return f"{Decimal(value).normalize():,f}"


def when(iso):
    return timezone.localtime(parse_datetime(iso)).strftime("%d %b %Y, %H:%M")


def render_receipt_pdf(data):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def hexc(value):
        return colors.HexColor(f"#{value}")

    ink, olive, yellow, soft = hexc(brand.INK), hexc(brand.OLIVE), hexc(brand.YELLOW), hexc(brand.YELLOW_SOFT)
    line_c, muted, text_c = hexc(brand.LINE), hexc(brand.MUTED), hexc(brand.TEXT)
    good, bad = hexc(brand.GOOD), hexc(brand.BAD)

    c = data["currency"]
    page_w = WIDTH_MM * mm
    margin = 5 * mm
    inner = page_w - 2 * margin
    header_h = 34 * mm
    reversed_sale = data["status"] == "reversed"

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=8, leading=10.5, textColor=text_c)
    small = ParagraphStyle("small", parent=body, fontSize=6.8, leading=8.5, textColor=muted)
    label = ParagraphStyle("label", parent=body, fontName="Helvetica-Bold", fontSize=6, leading=8, textColor=muted)
    label_right = ParagraphStyle("label_right", parent=label, alignment=TA_RIGHT)
    value = ParagraphStyle("value", parent=body, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=ink)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    item = ParagraphStyle("item", parent=body, fontName="Helvetica-Bold", textColor=ink)
    item_right = ParagraphStyle("item_right", parent=item, alignment=TA_RIGHT)
    center = ParagraphStyle("center", parent=body, alignment=TA_CENTER)

    def plain(cmds=()):
        return TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                *cmds,
            ]
        )

    def pairs(rows):
        return Table(
            [[Paragraph(_t(k), body), Paragraph(_t(v), right)] for k, v in rows],
            colWidths=[inner * 0.52, inner * 0.48],
            style=plain(),
        )

    def box(rows, widths, background, cmds=()):
        return Table(
            rows,
            colWidths=widths,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), background),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("ROUNDEDCORNERS", [5, 5, 5, 5]),
                    *cmds,
                ]
            ),
        )

    story = []

    # Receipt number with date (or VOID).
    number_style = ParagraphStyle("number", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=ink)
    status_style = ParagraphStyle(
        "status", parent=right, fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=bad if reversed_sale else ink
    )
    story += [
        Table(
            [
                [Paragraph("RECEIPT", label), Paragraph("STATUS" if reversed_sale else "DATE", label_right)],
                [
                    Paragraph(_t(data["number"]), number_style),
                    Paragraph(_t("VOID - sale reversed" if reversed_sale else when(data["posted_at"])), status_style),
                ],
            ],
            colWidths=[inner * 0.45, inner * 0.55],
            style=plain([("VALIGN", (0, 1), (-1, 1), "MIDDLE")]),
        ),
        Spacer(1, 3 * mm),
    ]

    # Customer and staff on a soft yellow card.
    story += [
        Table(
            [
                [Paragraph("CUSTOMER", label), Paragraph("SERVED BY", label)],
                [Paragraph(_t(data["customer_name"]), value), Paragraph(_t(data["created_by_name"]), value)],
            ],
            colWidths=[inner / 2, inner / 2],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), soft),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, 0), 5),
                    ("TOPPADDING", (0, 1), (-1, 1), 0),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
                    ("LINEAFTER", (0, 0), (0, -1), 0.5, hexc("FCDC8B")),
                    ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                ]
            ),
        ),
        Spacer(1, 4 * mm),
    ]

    # Items.
    item_rows, item_cmds = [], []
    for index, line in enumerate(data["lines"]):
        detail = f"{quantity(line['quantity'])} x {money(line['unit_price'], c)}"
        if Decimal(line["discount"]) > 0:
            detail += f"  (discount {money(line['discount'], c)})"
        item_rows += [
            [Paragraph(_t(line["description"]), item), Paragraph(_t(money(line["line_total"], c)), item_right)],
            [Paragraph(_t(detail), small), ""],
        ]
        item_cmds += [
            ("TOPPADDING", (0, 2 * index), (-1, 2 * index), 4),
            ("BOTTOMPADDING", (0, 2 * index + 1), (-1, 2 * index + 1), 4),
            ("LINEBELOW", (0, 2 * index + 1), (-1, 2 * index + 1), 0.4, line_c),
        ]
    story += [
        Table(
            [[Paragraph("ITEMS", label), Paragraph("AMOUNT", label_right)]],
            colWidths=[inner * 0.62, inner * 0.38],
            style=plain([("LINEBELOW", (0, 0), (-1, 0), 1, ink), ("BOTTOMPADDING", (0, 0), (-1, 0), 3)]),
        ),
        Table(item_rows, colWidths=[inner * 0.62, inner * 0.38], style=plain(item_cmds)),
        Spacer(1, 3 * mm),
    ]

    # Subtotal and discount.
    adjustments = []
    if Decimal(data["line_discount_total"]) > 0 or Decimal(data["sale_discount"]) > 0:
        adjustments.append(("Subtotal", money(data["subtotal"], c)))
    if Decimal(data["sale_discount"]) > 0:
        adjustments.append(("Discount", f"- {money(data['sale_discount'], c)}"))
    if adjustments:
        story += [pairs(adjustments), Spacer(1, 1.5 * mm)]

    # Total: dark pill with the amount in brand yellow.
    total_label = ParagraphStyle("total_label", parent=body, fontName="Helvetica-Bold", textColor=hexc("FCDC8B"))
    total_value = ParagraphStyle("total_value", parent=right, fontName="Helvetica-Bold", fontSize=12.5, leading=15, textColor=yellow)
    story += [
        box([[Paragraph("TOTAL", total_label), Paragraph(_t(money(data["total"], c)), total_value)]], [inner * 0.4, inner * 0.6], ink),
        Spacer(1, 3 * mm),
    ]

    # Payments.
    pay_rows = []
    for p in (p for p in data["payments"] if p["status"] == "posted"):
        pay_rows.append((f"Paid - {p['method_label']}" + (f" ({p['reference']})" if p["reference"] else ""), money(p["amount"], c)))
        if p["amount_tendered"]:
            pay_rows += [("Cash given", money(p["amount_tendered"], c)), ("Change", money(p["change"], c))]
    if pay_rows:
        story += [pairs(pay_rows), Spacer(1, 2.5 * mm)]

    # Balance due (red) or paid in full (green).
    if not reversed_sale:
        due = Decimal(data["balance_due"])
        badge = ParagraphStyle("badge", parent=body, fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=bad if due > 0 else good)
        badge_right = ParagraphStyle("badge_right", parent=badge, alignment=TA_RIGHT)
        cells = (
            [Paragraph("BALANCE DUE", badge), Paragraph(_t(money(data["balance_due"], c)), badge_right)]
            if due > 0
            else [Paragraph("PAID IN FULL", badge), Paragraph("Thank you", badge_right)]
        )
        story.append(box([cells], [inner * 0.5, inner * 0.5], hexc("FEF3F2") if due > 0 else hexc("ECFDF3")))

    story += [
        Spacer(1, 5 * mm),
        Paragraph(f"<b>{_t(THANKS)}</b>", ParagraphStyle("thanks", parent=center, textColor=ink)),
        Paragraph(
            "Keep smiling!", ParagraphStyle("smile", parent=center, fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=olive)
        ),
    ]

    # The page is exactly as long as the receipt, so thermal printers waste no paper.
    content_h = sum(f.wrap(inner, 10_000)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in story)
    footer_h = 9 * mm
    page_h = header_h + 6 * mm + content_h + footer_h + 12 + 3 * mm  # 12 pt: the frame's own top+bottom padding

    def decorate(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(ink)
        canvas.rect(0, page_h - header_h, page_w, header_h, stroke=0, fill=1)
        canvas.saveState()
        clip = canvas.beginPath()
        clip.rect(0, page_h - header_h, page_w, header_h)
        canvas.clipPath(clip, stroke=0, fill=0)
        canvas.setFillColor(hexc("2B1A10"))
        canvas.circle(page_w - 6 * mm, page_h - 2 * mm, 20 * mm, stroke=0, fill=1)
        canvas.restoreState()
        if brand.LOGO_ON_DARK.exists():
            canvas.drawImage(str(brand.LOGO_ON_DARK), (page_w - 17 * mm) / 2, page_h - 19.5 * mm, 17 * mm, 17 * mm, mask="auto")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawCentredString(page_w / 2, page_h - 25 * mm, data["organization_name"])
        canvas.setFillColor(hexc("FCDC8B"))
        canvas.setFont("Helvetica", 6.3)
        canvas.drawCentredString(page_w / 2, page_h - 29.5 * mm, brand.TAGLINE.replace("·", "-"))
        canvas.setFillColor(yellow)
        canvas.rect(0, page_h - header_h - 1.4 * mm, page_w, 1.4 * mm, stroke=0, fill=1)
        if reversed_sale:
            canvas.saveState()
            canvas.translate(page_w / 2, page_h / 2)
            canvas.rotate(28)
            canvas.setFillColor(hexc("F04438"))
            canvas.setFillAlpha(0.14)
            canvas.setFont("Helvetica-Bold", 44)
            canvas.drawCentredString(0, 0, "VOID")
            canvas.restoreState()
        canvas.setFillColor(yellow)
        canvas.rect(0, 0, page_w, 2.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 6)
        canvas.drawCentredString(page_w / 2, 4.6 * mm, f"Receipt {data['number']} - keep it for your records")
        canvas.restoreState()

    buffer = BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=(page_w, page_h),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=header_h + 6 * mm,
        bottomMargin=footer_h,
        title=f"Receipt {data['number']}",
        author=data["organization_name"],
    ).build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
