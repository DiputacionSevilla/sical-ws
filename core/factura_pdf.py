# core/factura_pdf.py
import io
from typing import Dict, Any, List

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_RIGHT

def _para(text: str, style):
    return Paragraph(text or "N/A", style)

def generate_resumen_factura_pdf(payload: Dict[str, Any]) -> bytes:
    """
    Genera un PDF 'Resumen de Factura' a partir de un dict recibido por API.
    Estructura esperada (claves principales):
      - factura: { numero, fecha, moneda, clase, periodo: {inicio, fin} }
      - registro: { num_rcf, fecha_hora_registro, num_registro, tipo_registro (opcional) }
      - emisor: { Nombre, NIF, Dirección, Poblacion, Cod.Postal, Provincia }
      - receptor: { Nombre, NIF, Dirección, OfiCont, OrgGest, UndTram } (opcional)
      - texto1: str   (detalle de la factura)
      - totales: { TotalGrossAmount, TotalGeneralDiscounts, TotalGrossAmountBeforeTaxes,
                   TotalTaxOutputs, TotalTaxesWithheld, InvoiceTotal,
                   TotalOutstandingAmount, TotalExecutableAmount } (cualesquiera presentes)

    Devuelve: bytes del PDF.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18
    )

    styles = getSampleStyleSheet()
    styleH = styles['Heading1']
    styleN = styles['Normal']
    styleN.fontSize = 8
    styleN.leading = 10
    header_cell = ParagraphStyle('header_cell', parent=styleN, alignment=1, fontSize=8, leading=10)
    right_align = ParagraphStyle('right_align', parent=styleN, alignment=TA_RIGHT)

    elements: List[Any] = []

    # -------- Cabecera --------
    factura = payload.get("factura", {}) or {}
    periodo = factura.get("periodo", {}) or {}
    registro = payload.get("registro", {}) or {}

    titulo = Paragraph("Resumen de Factura", styleH)
    info_factura = Paragraph(
        f"<b>Fecha de Emisión:</b> {factura.get('fecha','N/A')} "
        f"<b>Número:</b> {factura.get('numero','N/A')}<br/>"
        f"<b>Clase de factura:</b> {factura.get('clase','N/A')} "
        f"<b>Moneda:</b> {factura.get('moneda','N/A')}<br/>"
        f"<b>Periodo de facturación:</b> {periodo.get('inicio','N/A')} – {periodo.get('fin','N/A')}",
        styleN
    )
    info_registro = Paragraph(
        f"<b>Num. RCF:</b> {registro.get('num_rcf','N/A')}<br/>"
        f"<b>Fecha y hora RCF:</b> {registro.get('fecha_hora_registro','N/A')}<br/><br/>"
        f"<b>Num.Registro:</b> {registro.get('num_registro','N/A')}<br/>"
        f"<b>Fecha y hora Registro:</b> {registro.get('tipo_registro','') or '—'}",
        styleN
    )

    table_info = Table([[[titulo, info_factura], info_registro]], colWidths=[doc.width * 0.6, doc.width * 0.4])
    table_info.setStyle(TableStyle([
        ('BOX', (1, 0), (1, 0), 1, colors.black),
        ('INNERGRID', (1, 0), (1, 0), 0.5, colors.grey),
        ('BACKGROUND', (1, 0), (1, 0), colors.whitesmoke),
        ('VALIGN', (0, 0), (-1, -1), 'TOP')
    ]))
    elements.append(table_info)
    elements.append(Spacer(1, 12))

    # -------- Emisor / Receptor --------
    emisor = payload.get("emisor", {}) or {}
    receptor = payload.get("receptor", {}) or {}

    data_parties = [
        [Paragraph("<b>EMISOR</b>", styleN), Paragraph("<b>RECEPTOR</b>", styleN)],
        [
            Paragraph(
                f"<b>Nombre:</b> {emisor.get('Nombre','N/A')}<br/>"
                f"<b>NIF:</b> {emisor.get('NIF','N/A')}<br/>"
                f"<b>Dirección:</b> {emisor.get('Dirección','N/A')}<br/>"
                f"<b>Población:</b> {emisor.get('Poblacion','N/A')}<br/>"
                f"<b>Cod.Postal:</b> {emisor.get('Cod.Postal','N/A')}<br/>"
                f"<b>Provincia:</b> {emisor.get('Provincia','N/A')}",
                styleN
            ),
            Paragraph(
                f"<b>Nombre:</b> {receptor.get('Nombre','N/A')}<br/>"
                f"<b>NIF:</b> {receptor.get('NIF','N/A')}<br/>"
                f"<b>Dirección:</b> {receptor.get('Dirección','N/A')}<br/>"
                f"<b>Ofi.Cont.:</b> {receptor.get('OfiCont','N/A')}<br/>"
                f"<b>Org.Gest:</b> {receptor.get('OrgGest','N/A')}<br/>"
                f"<b>Und.Tram:</b> {receptor.get('UndTram','N/A')}",
                styleN
            )
        ]
    ]
    table_parties = Table(data_parties, colWidths=[doc.width/2.0, doc.width/2.0])
    table_parties.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)
    ]))
    elements.append(table_parties)
    elements.append(Spacer(1, 12))

    # -------- Detalle (texto1) --------
    texto1 = (payload.get("texto1") or "").strip()
    elements.append(Paragraph("<b>Detalle</b>", styleN))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph(texto1 if texto1 else "—", styleN))
    elements.append(Spacer(1, 12))

    # -------- Totales --------
    totals = payload.get("totales", {}) or {}
    if totals:
        def V(key, default="N/A"):
            return str(totals.get(key, default))

        left_data = [
            [Paragraph("<b>Importe bruto total:</b>", styleN), _para(V("TotalGrossAmount"), right_align)],
            [Paragraph("<b>Descuentos generales:</b>", styleN), _para(V("TotalGeneralDiscounts"), right_align)],
            [Paragraph("<b>Retenciones:</b>", styleN), _para(V("TotalTaxesWithheld"), right_align)],
        ]
        right_data = [
            [Paragraph("<b>Base imponible antes de impuestos:</b>", styleN), _para(V("TotalGrossAmountBeforeTaxes"), right_align)],
            [Paragraph("<b>Importe de impuestos:</b>", styleN), _para(V("TotalTaxOutputs"), right_align)],
            [Paragraph("<b>Importe total factura:</b>", styleN), _para(V("InvoiceTotal"), right_align)],
        ]

        half = doc.width / 2.0
        left_table = Table(left_data, colWidths=[half * 0.70, half * 0.30])
        left_table.setStyle(TableStyle([
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))

        right_table = Table(right_data, colWidths=[half * 0.70, half * 0.30])
        right_table.setStyle(TableStyle([
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))

        totals_table = Table([[left_table, right_table]], colWidths=[half, half])
        totals_table.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 1, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        elements.append(totals_table)
        elements.append(Spacer(1, 10))

    # -------- Pie simple --------
    def _add_footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(_doc.leftMargin, 20, "RESUMEN REPRESENTATIVO DE LA FACTURA.")
        canvas.restoreState()

    doc.build(elements, onFirstPage=_add_footer, onLaterPages=_add_footer)
    buffer.seek(0)
    return buffer.getvalue()
