# core/datosfactura_pdf.py
from __future__ import annotations
import io
import os
from typing import Dict, Any, List
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

GREEN = colors.Color(0.88, 0.94, 0.88)       # cabeceras bloques
DARK = colors.HexColor("#006400")            # título verde oscuro

def _styles():
    styles = getSampleStyleSheet()
    base = styles["Normal"]; base.fontSize = 9; base.leading = 12
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=13, textColor=DARK)
    label = ParagraphStyle("Label", parent=base, fontName="Helvetica-Bold")
    return base, h1, label

def _resolve_logo_path(datos: Dict[str, Any]) -> str | None:
    p = (datos.get("logo_path") or "").strip()
    if p and os.path.exists(p):
        return p
    area_code = (datos.get("area_code") or "").strip()
    if area_code:
        p2 = os.path.join("images", f"logo_{area_code}.png")
        if os.path.exists(p2):
            return p2
    p3 = os.path.join("images", "logo.png")
    if os.path.exists(p3):
        return p3
    return None

def build_pdf(datos: Dict[str, Any]) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=40, bottomMargin=36)
    base, h1, label = _styles()
    elems: List[Any] = []

    g = datos["generales"]

    # Cabecera con logo + título
    logo_path = _resolve_logo_path(datos)
    if logo_path:
        try:
            logo_obj = Image(logo_path, width=40, height=40)
        except Exception:
            logo_obj = Paragraph("LOGO", base)
    else:
        logo_obj = Paragraph("LOGO", base)

    title_para = Paragraph("Resumen de Factura", h1)
    head_tbl = Table([[logo_obj, title_para]], colWidths=[2.0 * cm, doc.width - 2.0 * cm])
    head_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 6),
    ]))
    elems += [head_tbl, Spacer(1, 6)]

    # Bloque: Generales
    t = Table([[Paragraph("DATOS GENERALES", label)]], colWidths=[doc.width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("BOX", (0, 0), (-1, -1), 1, DARK)
    ]))
    elems.append(t)

    # Usamos los campos "display" con (FACe) / (SIDERAL)
    num_reg_disp = g.get("num_registro_display") or ""
    fec_reg_disp = g.get("fecha_registro_display") or ""

    rows = [
        [Paragraph("<b>Nº Reg. SICAL:</b>", label), Paragraph(str(g.get("nfacreg","")), base)],
        [Paragraph("<b>Nº Reg. FACe / E.S.:</b>", label), Paragraph(num_reg_disp, base)],
        [Paragraph("<b>Fecha Reg. FACe:</b>", label), Paragraph(fec_reg_disp, base)],
        [Paragraph("<b>Tercero:</b>", label), Paragraph(f"{g.get('tercero_codigo','')} - {g.get('tercero_nombre','')}", base)],
        [Paragraph("<b>Endosatario:</b>", label), Paragraph(f"{g.get('endosatario_codigo','') or ''} - {g.get('endosatario_nombre','') or ''}", base)],
        [Paragraph("<b>Nº de Factura:</b>", label), Paragraph(g.get("num_factura_proveedor",""), base)],
        [Paragraph("<b>Fecha de Factura:</b>", label), Paragraph(g.get("fecha_factura",""), base)],
        [Paragraph("<b>Resolución:</b>", label), Paragraph(g.get("resolucion",""), base)],
        [Paragraph("<b>Nº Exp.:</b>", label), Paragraph(g.get("expediente",""), base)],
        [Paragraph("<b>Concepto:</b>", label), Paragraph(g.get("concepto",""), base)],
    ]
    tg = Table(rows, colWidths=[doc.width * 0.28, doc.width * 0.72])
    tg.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elems += [tg, Spacer(1, 8)]

    # Bloque: Totales
    t2 = Table([[Paragraph("TOTALES", label)]], colWidths=[doc.width])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("BOX", (0, 0), (-1, -1), 1, DARK)
    ]))
    elems.append(t2)

    tot_rows = [
        [Paragraph("<b>Importe Total:</b>", label), Paragraph(g.get("importe_total",""), base)],   # NBASIMP
        [Paragraph("<b>IVA:</b>", label), Paragraph(g.get("iva",""), base)],                       # NFACIVA
        [Paragraph("<b>Descuento:</b>", label), Paragraph(g.get("descuento",""), base)],           # DESCUENTO
        [Paragraph("<b>Importe Líquido:</b>", label), Paragraph(g.get("importe_liquido",""), base)]# NFACIMP
    ]
    tt = Table(tot_rows, colWidths=[doc.width * 0.35, doc.width * 0.65])
    tt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    elems += [tt, Spacer(1, 8)]

    # Bloque: Aplicaciones
    t3 = Table([[Paragraph("DETALLE DE APLICACIONES", label)]], colWidths=[doc.width])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("BOX", (0, 0), (-1, -1), 1, DARK)
    ]))
    elems.append(t3)

    apl = datos.get("aplicaciones", []) or []
    if apl:
        r = [[
            Paragraph("<b>Orgánica</b>", base),
            Paragraph("<b>Funcional</b>", base),
            Paragraph("<b>Económica</b>", base),
            Paragraph("<b>Referencia</b>", base),
            Paragraph("<b>Cuenta</b>", base),
            Paragraph("<b>Importe</b>", base),
        ]]
        for a in apl:
            r.append([
                a.get("organica", ""),
                a.get("funcional", ""),
                a.get("economica", ""),
                a.get("referencia", "") or "",
                a.get("cuenta", "") or "",
                a.get("importe_fmt", ""),
            ])
        tapl = Table(r, colWidths=[
            doc.width * 0.14, doc.width * 0.14, doc.width * 0.14,
            doc.width * 0.20, doc.width * 0.18, doc.width * 0.20
        ])
        tapl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ]))
        elems.append(tapl)
    else:
        elems.append(Paragraph("No hay aplicaciones asociadas.", base))
    elems += [Spacer(1, 8)]

    # Bloque: Descuentos
    t4 = Table([[Paragraph("DETALLE DE DESCUENTOS", label)]], colWidths=[doc.width])
    t4.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("BOX", (0, 0), (-1, -1), 1, DARK)
    ]))
    elems.append(t4)

    dct = datos.get("descuentos", []) or []
    if dct:
        r = [[
            Paragraph("<b>Año</b>", base),
            Paragraph("<b>Naturaleza</b>", base),
            Paragraph("<b>Aplicación</b>", base),
            Paragraph("<b>Base Imp.</b>", base),
            Paragraph("<b>%</b>", base),
            Paragraph("<b>Importe</b>", base),
            Paragraph("<b>Cuenta</b>", base),
        ]]
        for d in dct:
            r.append([
                d.get("anio", ""),
                d.get("naturaleza", ""),
                d.get("aplicacion", ""),
                d.get("base_imponible_fmt", ""),
                d.get("porcentaje_fmt", ""),
                d.get("importe_fmt", ""),
                d.get("cuenta", ""),
            ])
        tdct = Table(r, colWidths=[
            doc.width * 0.10, doc.width * 0.18, doc.width * 0.20,
            doc.width * 0.16, doc.width * 0.10, doc.width * 0.14, doc.width * 0.12
        ])
        tdct.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ]))
        elems.append(tdct)
    else:
        elems.append(Paragraph("No hay descuentos aplicados.", base))

    doc.build(elems)
    buf.seek(0)
    return buf
