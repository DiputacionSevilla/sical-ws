# core/pdf.py
import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm

# Tipografías compactas
FONT_SIZE_BASE = 9
LEADING_BASE   = 12
TITLE_SIZE     = 11

# Espaciados verticales (pt)
SP_AFTER_TITLE        = 14
SP_AFTER_ARTICLE      = 12
SP_BETWEEN_BLOCKS     = 12
SP_BETWEEN_ARTICLES   = 10
SP_AFTER_LAST_ARTICLE = 18

def _html_escape(text: str) -> str:
    if text is None:
        return ""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

def generate_acta_pdf(data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm
    )

    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]; style_normal.fontSize = FONT_SIZE_BASE; style_normal.leading = LEADING_BASE
    style_bold = ParagraphStyle(name="Bold", parent=style_normal, fontName="Helvetica-Bold")
    style_title = ParagraphStyle(name="Title", parent=style_bold, alignment=1, fontSize=TITLE_SIZE)
    green_fill = colors.Color(red=0.88, green=0.94, blue=0.88)
    green_dark = colors.Color(red=0.60, green=0.75, blue=0.60)

    elements = []

    # Cabecera con logo de área y nombre de área
    logo_obj = None
    if data.get("area_logo"):
        try:
            logo_obj = Image(data["area_logo"], width=100, height=100)
        except Exception:
            logo_obj = None
    if not logo_obj:
        try:
            logo_obj = Image("images/logo.png", width=100, height=100)
        except Exception:
            logo_obj = Paragraph(" ", style_normal)

    # --- Cabecera: logo + (opcional) unidad, con logo totalmente pegado a la izquierda ---
    LOGO_W, LOGO_H = 100, 100  # ajusta si tu imagen tiene otro tamaño

    # Si no quieres mostrar el nombre de área (va en el logo), déjalo vacío
    area_text = ""  # ya no mostramos el nombre de área
    unidad_text = data.get('unidad', '') or ""

    area_unidad = Paragraph(unidad_text, style_normal)  # solo unidad (si hay)

    # La 1ª columna mide EXACTAMENTE el ancho del logo → sin “dentado”
    cabecera_tabla = Table(
        [[logo_obj, area_unidad]],
        colWidths=[LOGO_W, doc.width - LOGO_W],
        rowHeights=[max(LOGO_H, 0)]
    )

    # Quita padding de la celda del logo y deja un pequeño espacio hacia el texto
    cabecera_tabla.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 6),   # separación logo ↔ texto
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('ALIGN',        (0, 0), (0, 0), 'LEFT'),
        ('ALIGN',        (1, 0), (1, 0), 'LEFT'),
    ]))
    elements.append(cabecera_tabla)
    elements.append(Spacer(1, 8))

    # Título dinámico según conformidad
    es_no_conforme = (data.get("resultado_conformidad") == "no_conforme")
    if es_no_conforme:
        titulo_html = "INFORME DE <font color='red'><b>NO</b></font> CONFORMIDAD DE LA FACTURA"
    else:
        titulo_html = "INFORME DE CONFORMIDAD DE LA FACTURA"
    elements.append(Paragraph(titulo_html, style_title))
    elements.append(Spacer(1, SP_AFTER_TITLE))

    # PRIMERO
    texto1 = (
        "<b>PRIMERO.</b> En la fecha y hora que a continuación se relaciona, "
        "se ha recibido en esta Administración la siguiente factura."
    )
    elements.append(Paragraph(texto1, style_normal))
    elements.append(Spacer(1, SP_AFTER_ARTICLE))

    # Registro de entrada
    registro_data = [
        [Paragraph("<b><u>REGISTRO DE ENTRADA</u></b>", style_bold), ""],
        [Paragraph(f"<b>Punto de entrada:</b> {data.get('punto_entrada', '')}", style_normal),
         Paragraph(f"<b>Nº Registro:</b> {data.get('id_punto_entrada', '')}", style_normal)],
        [Paragraph(f"<b>Fecha y hora:</b> {data.get('fecha_hora_entrada', '')}", style_normal),
         Paragraph(f"<b>RCF:</b> {data.get('num_rcf', '')}", style_normal)],
    ]

    # Ancho de columnas: 60% / 40% para dar más espacio al Nº Registro
    tabla_registro = Table(registro_data, colWidths=[doc.width * 0.60, doc.width * 0.40])
    tabla_registro.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), green_fill),
        ('SPAN', (0, 0), (-1, 0)),
        ('BOX', (0, 0), (-1, -1), 1, green_dark),
        ('INNERGRID', (0, 1), (-1, -1), 0.5, green_dark),

        # Ajustes de padding para maximizar el espacio útil
        ('LEFTPADDING',  (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),

        # Alinear arriba por si hay saltos de línea
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(tabla_registro)
    elements.append(Spacer(1, SP_BETWEEN_BLOCKS))

    # === (Bloque de aplicaciones presupuestarias actualmente desactivado en este archivo) ===
    elements.append(Spacer(1, SP_BETWEEN_BLOCKS))

    # Datos de la factura
    datos_factura_data = [
        [Paragraph("<b><u>DATOS DE LA FACTURA</u></b>", style_bold), ""],
        [Paragraph(f"<b>Proveedor:</b> {data.get('proveedor', '')}", style_normal),
         Paragraph(f"<b>NIF:</b> {data.get('nif_proveedor', '')}", style_normal)],
        [Paragraph(f"<b>Factura nº:</b> {data.get('vfacnum','')} <b>de fecha:</b> {data.get('fecha_expedicion','')}", style_normal),
         Paragraph(f"<b>Importe:</b> {data.get('importe_total', '')}", style_normal)],
        [Paragraph("<b>Concepto:</b><br/>" + (data.get('concepto', '') or '').replace('\n', ' '), style_normal), ""]
    ]
    tabla_factura = Table(datos_factura_data, colWidths=[doc.width * 2 / 3, doc.width * 1 / 3])
    tabla_factura.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), green_fill),
        ('SPAN', (0, 0), (-1, 0)),
        ('SPAN', (0, 3), (-1, 3)),
        ('BOX', (0, 0), (-1, -1), 1, green_dark),
        ('INNERGRID', (0, 1), (-1, 2), 0.5, green_dark),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(tabla_factura)
    elements.append(Spacer(1, SP_BETWEEN_BLOCKS + 2))

    # SEGUNDO
    texto2 = (
        "<b>SEGUNDO.</b> En aplicación de la normativa presupuestaria local —artículo 59 del Real Decreto 500/1990, "
        "de 20 de abril, y artículo 189 del Texto Refundido de la Ley Reguladora de las Haciendas Locales, "
        "aprobado por Real Decreto Legislativo 2/2004, de 5 de marzo—, y de conformidad con lo previsto en el "
        "Artículo 28 de las Bases de Ejecución del Presupuesto, antes de proceder al reconocimiento de la obligación "
        "deberá acreditarse documentalmente ante el órgano competente que la prestación se ha efectuado o que el "
        "acreedor posee el derecho derivado del acuerdo que autorizó y comprometió el gasto."
    )
    elements.append(Paragraph(texto2, style_normal))
    elements.append(Spacer(1, SP_BETWEEN_ARTICLES))

    # TERCERO (condicional: conforme / no conforme)
    if es_no_conforme:
        texto3 = ("<b>TERCERO.</b> Realizadas las verificaciones oportunas, queda acreditado que la prestación "
                  "<font color='red'><b>NO</b></font> se ha llevado a cabo de manera CONFORME y en los términos establecidos.")
    else:
        texto3 = ("<b>TERCERO.</b> Realizadas las verificaciones oportunas, queda acreditado que la prestación "
                  "se ha llevado a cabo de manera <b>CONFORME</b> y en los términos establecidos.")
    elements.append(Paragraph(texto3, style_normal))
    elements.append(Spacer(1, 8))

    # Motivo de NO CONFORMIDAD (solo si aplica)
    if es_no_conforme:
        motivo = _html_escape(data.get("motivo_no_conformidad", "").strip())
        if motivo:
            elements.append(Paragraph(f"<b>Motivo de <u>NO CONFORMIDAD</u>:</b> {motivo}", style_normal))
            elements.append(Spacer(1, SP_AFTER_LAST_ARTICLE))
        else:
            elements.append(Spacer(1, SP_AFTER_LAST_ARTICLE))
    else:
        elements.append(Spacer(1, SP_AFTER_LAST_ARTICLE))

    # --------------------------
    # NUEVO: Bloque Observaciones (opcional, solo si viene texto)
    # --------------------------
    obs = (data.get("observaciones") or "").strip()
    if obs:
        # Título del bloque y contenido (escapando HTML básico y respetando saltos de línea)
        elements.append(Paragraph("<b>Observaciones:</b>", style_bold))
        obs_html = _html_escape(obs).replace("\n", "<br/>")
        elements.append(Paragraph(obs_html, style_normal))
        elements.append(Spacer(1, SP_BETWEEN_BLOCKS))
    # --------------------------

    # Pie
    def add_footer(canv, _doc):
        canv.saveState()
        canv.setFont("Helvetica-Bold", 9)
        text = ""
        width = canv.stringWidth(text, "Helvetica-Bold", 9)
        x = (A4[0] - width) / 2
        canv.drawString(x, 1.3 * cm, text)
        canv.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)
    return buffer
