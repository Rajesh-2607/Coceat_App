"""Printable bills: A4 and 80 mm thermal, English or Tamil. HTML built here, turned into a PDF by WeasyPrint.

Every piece of text that came from a user (names, addresses, notes) is HTML-escaped. Rendering is CPU work: callers
run ``render_pdf`` off the event loop (``asyncio.to_thread``), never inside a request coroutine.
"""

from decimal import Decimal
from html import escape
from typing import Literal

from app.modules.sales.schemas import BillLineOut, BillOut

PaperFormat = Literal["a4", "thermal"]
Lang = Literal["en", "ta"]

_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "tax_invoice": "TAX INVOICE",
        "bill_of_supply": "BILL OF SUPPLY",
        "cancelled": "CANCELLED",
        "bill_no": "Bill no.",
        "date": "Date",
        "customer": "Customer",
        "gstin": "GSTIN",
        "phone": "Phone",
        "place": "Place of supply (state code)",
        "item": "Item",
        "hsn": "HSN",
        "qty": "Qty",
        "rate": "Rate",
        "gst": "GST",
        "amount": "Amount",
        "taxable": "Taxable value",
        "cgst": "CGST",
        "sgst": "SGST",
        "igst": "IGST",
        "round_off": "Round off",
        "total": "Total",
        "paid": "Paid",
        "balance": "On credit",
        "thanks": "Thank you. Visit again.",
        "exempt_note": "Supply of goods exempt from GST.",
    },
    "ta": {
        "tax_invoice": "வரி விலைப்பட்டியல்",
        "bill_of_supply": "விநியோக பில்",
        "cancelled": "ரத்து செய்யப்பட்டது",
        "bill_no": "பில் எண்",
        "date": "தேதி",
        "customer": "வாடிக்கையாளர்",
        "gstin": "GSTIN",
        "phone": "தொலைபேசி",
        "place": "விநியோக இடம் (மாநிலக் குறியீடு)",
        "item": "பொருள்",
        "hsn": "HSN",
        "qty": "அளவு",
        "rate": "விலை",
        "gst": "GST",
        "amount": "தொகை",
        "taxable": "வரிக்குட்பட்ட மதிப்பு",
        "cgst": "CGST",
        "sgst": "SGST",
        "igst": "IGST",
        "round_off": "முழு ரூபாய்க்கு",
        "total": "மொத்தம்",
        "paid": "செலுத்தியது",
        "balance": "கடன்",
        "thanks": "நன்றி. மீண்டும் வருக.",
        "exempt_note": "GST விலக்கு பெற்ற பொருட்களின் விநியோகம்.",
    },
}


def money(paise: int) -> str:
    """Indian digit grouping: 123456789 paise -> '12,34,567.89'. Whole rupees drop the '.00'."""
    sign = "-" if paise < 0 else ""
    rupees, rest = divmod(abs(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{sign}{digits}" + (f".{rest:02d}" if rest else "")


def quantity(line: BillLineOut) -> str:
    """Base units back into the unit the price was quoted in: 12500 g at kg (1000 g) -> '12.5 kg'."""
    value = (Decimal(line.quantity_base) / Decimal(line.unit_base_factor)).quantize(Decimal("0.001"))
    return f"{format(value.normalize(), 'f')} {escape(line.unit_code)}"


def _rate_text(bp: int) -> str:
    whole, frac = divmod(bp, 100)
    return f"{whole}.{frac:02d}%".replace(".00%", "%")


def _css(fmt: PaperFormat) -> str:
    font = '"Noto Sans Tamil", "Noto Sans", "DejaVu Sans", sans-serif'
    if fmt == "thermal":
        page = "@page { size: 80mm auto; margin: 3mm; }"
        base = "body { font-size: 8.5pt; }"
    else:
        page = "@page { size: A4; margin: 14mm; }"
        base = "body { font-size: 10pt; }"
    return f"""
    {page}
    * {{ box-sizing: border-box; }}
    body {{ font-family: {font}; color: #111; margin: 0; }}
    {base}
    h1 {{ font-size: 1.5em; margin: 0; }}
    h2 {{ font-size: 1.1em; margin: 0.2em 0; letter-spacing: 0.04em; }}
    .center {{ text-align: center; }}
    .muted {{ color: #444; }}
    .row {{ display: flex; justify-content: space-between; gap: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
    th, td {{ padding: 3px 4px; vertical-align: top; }}
    th {{ border-top: 1px solid #111; border-bottom: 1px solid #111; text-align: left; }}
    td.n, th.n {{ text-align: right; white-space: nowrap; }}
    tr.line td {{ border-bottom: 1px dotted #aaa; }}
    .totals {{ margin-top: 8px; margin-left: auto; width: {"100%" if fmt == "thermal" else "55%"}; }}
    .totals td {{ padding: 2px 4px; }}
    .grand td {{ border-top: 1px solid #111; font-weight: bold; font-size: 1.15em; }}
    .stamp {{ margin: 8px 0; padding: 4px; border: 2px solid #b00; color: #b00; text-align: center;
              font-weight: bold; letter-spacing: 0.1em; }}
    .foot {{ margin-top: 12px; }}
    """


def render_html(bill: BillOut, *, fmt: PaperFormat = "a4", lang: Lang = "en") -> str:
    t = _TEXT[lang]
    tamil = lang == "ta"
    e = escape
    title = t["tax_invoice" if bill.doc_type == "tax_invoice" else "bill_of_supply"]
    thermal = fmt == "thermal"

    head = [f'<h1 class="center">{e(bill.seller_name)}</h1>']
    if bill.seller_address:
        head.append(f'<div class="center muted">{e(bill.seller_address)}</div>')
    contact = " · ".join(
        p
        for p in (
            f"{t['phone']}: {e(bill.seller_phone)}" if bill.seller_phone else "",
            f"{t['gstin']}: {e(bill.seller_gstin)}" if bill.seller_gstin else "",
        )
        if p
    )
    if contact:
        head.append(f'<div class="center muted">{contact}</div>')
    head.append(f'<h2 class="center">{title}</h2>')
    if bill.status == "void":
        head.append(f'<div class="stamp">{t["cancelled"]}</div>')

    meta = [
        f'<div class="row"><span>{t["bill_no"]}: <b>{e(bill.bill_number)}</b></span>'
        f"<span>{t['date']}: {bill.bill_date:%d-%m-%Y}</span></div>"
    ]
    if bill.party_name:
        who = f"{t['customer']}: <b>{e(bill.party_name)}</b>"
        extras = [
            f"{t['phone']}: {e(bill.party_phone)}" if bill.party_phone else "",
            f"{t['gstin']}: {e(bill.party_gstin)}" if bill.party_gstin else "",
            e(bill.party_address) if bill.party_address else "",
        ]
        meta.append(f"<div>{who}</div>")
        meta.extend(f'<div class="muted">{x}</div>' for x in extras if x)
    if bill.doc_type == "tax_invoice" and bill.place_of_supply:
        meta.append(f'<div class="muted">{t["place"]}: {e(bill.place_of_supply)}</div>')

    if thermal:
        header = f'<tr><th>{t["item"]}</th><th class="n">{t["qty"]}</th><th class="n">{t["amount"]}</th></tr>'
    else:
        header = (
            f'<tr><th>#</th><th>{t["item"]}</th><th>{t["hsn"]}</th><th class="n">{t["qty"]}</th>'
            f'<th class="n">{t["rate"]}</th><th class="n">{t["taxable"]}</th><th class="n">{t["gst"]}</th>'
            f'<th class="n">{t["amount"]}</th></tr>'
        )
    body = []
    for ln in bill.lines:
        name = e(ln.description_ta if tamil and ln.description_ta else ln.description)
        if thermal:
            body.append(
                f'<tr class="line"><td>{name}<br><span class="muted">{money(ln.unit_price_paise)}/{e(ln.unit_code)}'
                f"{' · ' + _rate_text(ln.gst_rate_bp) if ln.gst_rate_bp else ''}</span></td>"
                f'<td class="n">{quantity(ln)}</td><td class="n">{money(ln.total_paise)}</td></tr>'
            )
        else:
            body.append(
                f'<tr class="line"><td>{ln.line_no}</td><td>{name}</td><td>{e(ln.hsn_code or "")}</td>'
                f'<td class="n">{quantity(ln)}</td><td class="n">{money(ln.unit_price_paise)}/{e(ln.unit_code)}</td>'
                f'<td class="n">{money(ln.taxable_paise)}</td>'
                f'<td class="n">{_rate_text(ln.gst_rate_bp) if ln.gst_rate_bp else "-"}</td>'
                f'<td class="n">{money(ln.total_paise)}</td></tr>'
            )

    totals = []
    if bill.doc_type == "tax_invoice":
        totals.append(f'<tr><td>{t["taxable"]}</td><td class="n">{money(bill.taxable_paise)}</td></tr>')
        if bill.supply_type == "inter":
            totals.append(f'<tr><td>{t["igst"]}</td><td class="n">{money(bill.igst_paise)}</td></tr>')
        else:
            totals.append(f'<tr><td>{t["cgst"]}</td><td class="n">{money(bill.cgst_paise)}</td></tr>')
            totals.append(f'<tr><td>{t["sgst"]}</td><td class="n">{money(bill.sgst_paise)}</td></tr>')
    if bill.round_off_paise:
        sign = "+" if bill.round_off_paise > 0 else "-"
        totals.append(f'<tr><td>{t["round_off"]}</td><td class="n">{sign}{money(abs(bill.round_off_paise))}</td></tr>')
    totals.append(f'<tr class="grand"><td>{t["total"]}</td><td class="n">₹{money(bill.total_paise)}</td></tr>')
    totals.append(f'<tr><td>{t["paid"]}</td><td class="n">{money(bill.paid_paise)}</td></tr>')
    if bill.credit_paise:
        totals.append(f'<tr><td>{t["balance"]}</td><td class="n">{money(bill.credit_paise)}</td></tr>')

    notes = []
    if bill.doc_type == "bill_of_supply":
        notes.append(f'<div class="muted">{t["exempt_note"]}</div>')
    if bill.note:
        notes.append(f'<div class="muted">{e(bill.note)}</div>')

    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        f"<title>{e(bill.bill_number)}</title><style>{_css(fmt)}</style></head><body>"
        + "".join(head)
        + "".join(meta)
        + f"<table><thead>{header}</thead><tbody>{''.join(body)}</tbody></table>"
        + f'<table class="totals"><tbody>{"".join(totals)}</tbody></table>'
        + "".join(notes)
        + f'<div class="foot center muted">{t["thanks"]}</div></body></html>'
    )


def render_pdf(html: str) -> bytes:
    """HTML to PDF bytes (CPU-bound: call from a worker thread)."""
    from weasyprint import HTML  # imported here so the API still starts if the system libraries are missing

    pdf = HTML(string=html).write_pdf()
    assert isinstance(pdf, bytes)
    return pdf
