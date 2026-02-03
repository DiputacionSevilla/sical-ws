# core/xsig_pdf.py
import io
import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import BinaryIO, Optional, Dict
from dateutil import parser as date_parser

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, FrameBreak, KeepTogether,
    Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import cm


# ------------------------------
# Utilidades internas
# ------------------------------

def _extract_xml_from_xsig_bytes(xsig_bytes: bytes) -> bytes:
    """Extrae el bloque XML de un contenedor XSIG buscando el marcador '<?xml'."""
    xml_start = xsig_bytes.find(b"<?xml")
    xml_end = xsig_bytes.rfind(b">") + 1
    if xml_start != -1 and xml_end > xml_start:
        return xsig_bytes[xml_start:xml_end]
    # Si ya es XML puro o no se encuentra, devolvemos tal cual para intentar parseo
    return xsig_bytes


def _extract_signature_info_from_xml(xml_root: ET.Element) -> dict:
    """Extrae información de la firma electrónica si está presente en el XML."""
    try:
        ns = {
            'ds': 'http://www.w3.org/2000/09/xmldsig#',
            'xades': 'http://uri.etsi.org/01903/v1.3.2#'
        }

        cert_base64 = xml_root.findtext(".//ds:X509Certificate", default="", namespaces=ns)
        if not cert_base64:
            return {"estado": "No se encontró certificado"}

        cert_der = base64.b64decode(cert_base64)
        cert = x509.load_der_x509_certificate(cert_der, backend=default_backend())

        # Sujeto y emisor
        subject = cert.subject
        issuer = cert.issuer

        def _get_attr(name_oid, default="N/A"):
            try:
                return subject.get_attributes_for_oid(name_oid)[0].value
            except Exception:
                return default

        from cryptography.x509.oid import NameOID, ObjectIdentifier

        cn = _get_attr(NameOID.COMMON_NAME)
        try:
            nif = subject.get_attributes_for_oid(ObjectIdentifier("2.5.4.5"))[0].value
        except Exception:
            nif = "N/A"

        try:
            cert_issuer = issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        except Exception:
            cert_issuer = "No disponible"

        try:
            algorithm = cert.signature_hash_algorithm.name.upper()
        except Exception:
            algorithm = "N/A"

        signing_time_str = xml_root.findtext(".//xades:SigningTime", default="No especificada", namespaces=ns)

        # Ventanas de validez: usa *_utc si existen; si no, accede a las antiguas sin avisos
        try:
            # cryptography >= 41 expone propiedades aware
            valido_desde = cert.not_valid_before_utc
            valido_hasta = cert.not_valid_after_utc
        except AttributeError:
            # Sólo existen las antiguas (naive). Su acceso lanza DeprecationWarning: lo silenciamos localmente.
            import warnings
            from cryptography.utils import CryptographyDeprecationWarning
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
                nb = cert.not_valid_before
                na = cert.not_valid_after
            # Normalizamos a aware (UTC)
            valido_desde = nb.replace(tzinfo=timezone.utc) if nb.tzinfo is None else nb.astimezone(timezone.utc)
            valido_hasta = na.replace(tzinfo=timezone.utc) if na.tzinfo is None else na.astimezone(timezone.utc)

        if valido_desde.tzinfo is None:
            valido_desde = valido_desde.replace(tzinfo=timezone.utc)
        if valido_hasta.tzinfo is None:
            valido_hasta = valido_hasta.replace(tzinfo=timezone.utc)

        # Estado actual del certificado (en UTC)
        now = datetime.now(timezone.utc)
        if now < valido_desde:
            estado_actual = "Certificado aún no válido (vigencia futura)"
        elif now > valido_hasta:
            estado_actual = "Certificado caducado"
        else:
            estado_actual = "Certificado actualmente válido"

        # Validez en la fecha de firma
        try:
            signing_datetime = date_parser.parse(signing_time_str)
            if signing_datetime.tzinfo is None:
                signing_datetime = signing_datetime.replace(tzinfo=timezone.utc)
            else:
                signing_datetime = signing_datetime.astimezone(timezone.utc)

            if valido_desde <= signing_datetime <= valido_hasta:
                validez_en_firma = "Certificado válido en la fecha de la firma"
            else:
                validez_en_firma = "Certificado NO era válido en la fecha de la firma"
        except Exception as e:
            validez_en_firma = f"No se pudo validar la fecha de firma: {e}"

        return {
            "estado": "Firma encontrada",
            "firmante": cn,
            "nif": nif,
            "algoritmo": algorithm,
            "fecha_firma": signing_time_str,
            "valido_desde": valido_desde.strftime("%Y-%m-%d"),
            "valido_hasta": valido_hasta.strftime("%Y-%m-%d"),
            "estado_certificado": estado_actual,
            "validez_en_firma": validez_en_firma,
            "autoridad_certificadora": cert_issuer
        }
    except Exception as e:
        return {"estado": f"Error al extraer firma: {str(e)}"}


def _address_components(entity_root: Optional[ET.Element]) -> Dict[str, str]:
    """Devuelve componentes de dirección si existen (para enriquecer EMISOR/RECEPTOR/TERCERO)."""
    result = {"Dirección": "N/A", "Poblacion": "N/A", "Cod.Postal": "N/A", "Provincia": "N/A"}
    if entity_root is None:
        return result

    addr_es = entity_root.find("AddressInSpain")
    if addr_es is not None:
        address = addr_es.findtext("Address", default="") or ""
        postcode = addr_es.findtext("PostCode", default="") or ""
        town = addr_es.findtext("Town", default="") or ""
        province = addr_es.findtext("Province", default="") or ""
        country = addr_es.findtext("CountryCode", default="") or ""

        address_fmt = ", ".join([p for p in [address, f"{postcode} {town}".strip(), province, country] if p])
        result.update({
            "Dirección": address_fmt or "N/A",
            "Poblacion": town or "N/A",
            "Cod.Postal": postcode or "N/A",
            "Provincia": province or "N/A",
        })
        return result

    # OverseasAddress → sólo devolvemos Dirección compuesta
    addr_ov = entity_root.find("OverseasAddress")
    if addr_ov is not None:
        line = addr_ov.findtext("Address", default="") or ""
        post = addr_ov.findtext("PostCodeAndTown", default="") or ""
        prov = addr_ov.findtext("Province", default="") or ""
        country = addr_ov.findtext("CountryCode", default="") or ""
        address_fmt = ", ".join([p for p in [line, post, prov, country] if p]) or "N/A"
        result["Dirección"] = address_fmt
    return result


def _extract_party_full(parent: ET.Element, party_tag: str) -> Dict[str, str]:
    """Extrae Nombre, NIF y dirección (y componentes) de SellerParty/BuyerParty/ThirdParty."""
    party = parent.find(f".//{party_tag}")
    if party is None:
        return {}

    tax_id = party.findtext(".//TaxIdentification/TaxIdentificationNumber", default="N/A") or "N/A"

    legal = party.find(".//LegalEntity")
    individual = party.find(".//Individual")

    if legal is not None:
        name = (legal.findtext("CorporateName", default="") or "").strip() or "N/A"
        addr_parts = _address_components(legal)
    elif individual is not None:
        name = (
            (individual.findtext("Name", default="") or "").strip() + " " +
            (individual.findtext("FirstSurname", default="") or "").strip() + " " +
            (individual.findtext("SecondSurname", default="") or "").strip()
        ).strip() or "N/A"
        addr_parts = _address_components(individual)
    else:
        name = "N/A"
        addr_parts = {"Dirección": "N/A", "Poblacion": "N/A", "Cod.Postal": "N/A", "Provincia": "N/A"}

    out = {
        "Nombre": name,
        "NIF": tax_id,
        "Dirección": addr_parts.get("Dirección", "N/A"),
    }
    if "Poblacion" in addr_parts:
        out["Poblacion"] = addr_parts["Poblacion"]
    if "Cod.Postal" in addr_parts:
        out["Cod.Postal"] = addr_parts["Cod.Postal"]
    if "Provincia" in addr_parts:
        out["Provincia"] = addr_parts["Provincia"]
    return out


def _extract_invoice_data_from_xml(xml_root: ET.Element) -> dict:
    """Extrae datos de la factura del XML (Facturae) con tolerancia a campos ausentes."""
    emitter = _extract_party_full(xml_root, "SellerParty") or {
        "Nombre": "N/A", "NIF": "N/A", "Dirección": "N/A", "Poblacion": "N/A", "Cod.Postal": "N/A", "Provincia": "N/A"
    }
    receptor = _extract_party_full(xml_root, "BuyerParty") or {
        "Nombre": "N/A", "NIF": "N/A", "Dirección": "N/A"
    }

    # Centros administrativos
    buyer_party = xml_root.find(".//BuyerParty")
    destinos = []
    if buyer_party is not None:
        for admin in buyer_party.findall(".//AdministrativeCentres/AdministrativeCentre"):
            code = admin.findtext("CentreCode", default="N/A")
            desc = admin.findtext("Name", default="N/A")
            destinos.append(f"{code} - {desc}")
    receptor["OfiCont"] = destinos[0] if len(destinos) > 0 else "N/A"
    receptor["OrgGest"] = destinos[1] if len(destinos) > 1 else "N/A"
    receptor["Und.Tram"] = destinos[2] if len(destinos) > 2 else "N/A"
    receptor["UndTram"] = receptor["Und.Tram"]

    tercero = _extract_party_full(xml_root, "ThirdParty")  # dict o {}

    invoice_element = xml_root.find(".//Invoices/Invoice")
    if invoice_element is not None:
        invoice_number = invoice_element.findtext(".//InvoiceHeader/InvoiceNumber", default="N/A")
        invoice_series = invoice_element.findtext(".//InvoiceHeader/InvoiceSeriesCode", default="") or ""
        invoice_type = invoice_element.findtext(".//InvoiceHeader/InvoiceDocumentType", default="N/A")
        invoice_currency = invoice_element.findtext(".//InvoiceIssueData/InvoiceCurrencyCode", default="N/A")
        raw_date = invoice_element.findtext(".//InvoiceIssueData/IssueDate", default="N/A")
        invoice_class = invoice_element.findtext(".//InvoiceHeader/InvoiceClass", default="N/A")

        invoice_class_map = {
            "OO": "Original", "OR": "Original Rectificativa", "OC": "Original Recapitulativa",
            "CO": "Duplicado Original", "CR": "Duplicado Rectificativa", "CC": "Duplicado Recapitulativa"
        }
        invoice_class_desc = invoice_class_map.get(invoice_class, "N/A")

        try:
            issue_date = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            issue_date = raw_date
        invoice_number = f"{invoice_series}{invoice_number}"

        issue_data = invoice_element.find("InvoiceIssueData")
        if issue_data is not None:
            invp = issue_data.find("InvoicingPeriod")
            if invp is not None:
                start = invp.findtext("StartDate", default="") or ""
                end = invp.findtext("EndDate", default="") or ""

                def _fmt_date(d):
                    try:
                        return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")
                    except Exception:
                        return d or "N/A"

                invoicing_period = {"Inicio": _fmt_date(start), "Fin": _fmt_date(end)}
            else:
                invoicing_period = {}
        else:
            invoicing_period = {}
    else:
        invoice_number = issue_date = invoice_type = invoice_currency = "N/A"
        invoice_class_desc = "N/A"
        invoicing_period = {}

    invoice_additional_info = (xml_root.findtext(".//AdditionalData/InvoiceAdditionalInformation", default="") or "").strip()
    legal_references = [ref.text.strip() for ref in xml_root.findall(".//LegalLiterals/LegalReference") if ref.text and ref.text.strip() != ""]

    totals = {}
    taxes_withheld_details = []
    if invoice_element is not None:
        invoice_totals = invoice_element.find(".//InvoiceTotals")
        if invoice_totals is not None:
            totals["TotalGrossAmount"] = invoice_totals.findtext("TotalGrossAmount", default="0.00")
            totals["TotalGeneralDiscounts"] = invoice_totals.findtext("TotalGeneralDiscounts", default="0.00")
            totals["TotalGrossAmountBeforeTaxes"] = invoice_totals.findtext("TotalGrossAmountBeforeTaxes", default="N/A")
            totals["TotalTaxOutputs"] = invoice_totals.findtext("TotalTaxOutputs", default="N/A")
            totals["TotalTaxesWithheld"] = invoice_totals.findtext("TotalTaxesWithheld", default="N/A")
            totals["InvoiceTotal"] = invoice_totals.findtext("InvoiceTotal", default="N/A")
            totals["TotalOutstandingAmount"] = invoice_totals.findtext("TotalOutstandingAmount", default="N/A")
            totals["TotalExecutableAmount"] = invoice_totals.findtext("TotalExecutableAmount", default="N/A")

        taxes_withheld = invoice_element.find(".//TaxesWithheld")
        if taxes_withheld is not None:
            for tax in taxes_withheld.findall("Tax"):
                code = (tax.findtext("TaxTypeCode", default="") or "").strip()
                rate = (tax.findtext("TaxRate", default="") or "").strip()
                amount = (tax.findtext(".//TaxAmount/TotalAmount", default="") or "").strip()
                taxable_base = (tax.findtext(".//TaxableBase/TotalAmount", default="") or "").strip()
                taxes_withheld_details.append({
                    "code": code,
                    "rate": rate,
                    "amount": amount,
                    "taxable_base": taxable_base
                })

    # Desglose de impuestos repercutidos (TaxesOutputs) - IVA por tipo
    taxes_output_details = []
    if invoice_element is not None:
        taxes_outputs = invoice_element.find(".//TaxesOutputs")
        if taxes_outputs is not None:
            for tax in taxes_outputs.findall("Tax"):
                taxes_output_details.append({
                    "type_code": (tax.findtext("TaxTypeCode", default="01") or "01").strip(),
                    "rate": (tax.findtext("TaxRate", default="21") or "21").strip(),
                    "base": (tax.findtext(".//TaxableBase/TotalAmount", default="0") or "0").strip(),
                    "amount": (tax.findtext(".//TaxAmount/TotalAmount", default="0") or "0").strip(),
                    "surcharge": (tax.findtext("EquivalenceSurcharge", default="0") or "0").strip(),
                    "surcharge_amount": (tax.findtext(".//EquivalenceSurchargeAmount/TotalAmount", default="0") or "0").strip()
                })

    # Detalles de pago (PaymentDetails)
    payment_details = {}
    if invoice_element is not None:
        payment = invoice_element.find(".//PaymentDetails/Installment")
        if payment is not None:
            due_date_raw = (payment.findtext("InstallmentDueDate", default="") or "").strip()
            try:
                due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").strftime("%d/%m/%Y") if due_date_raw else ""
            except Exception:
                due_date = due_date_raw

            payment_means_code = (payment.findtext("PaymentMeans", default="") or "").strip()
            payment_means_map = {
                "01": "Al contado", "02": "Recibo domiciliado", "03": "Recibo",
                "04": "Transferencia", "05": "Letra aceptada", "06": "Crédito documentario",
                "07": "Contrato adjudicación", "08": "Letra de cambio", "09": "Pagaré a la orden",
                "10": "Pagaré no a la orden", "11": "Cheque", "12": "Reposición",
                "13": "Especiales", "14": "Compensación", "15": "Giro postal",
                "16": "Cheque conformado", "17": "Cheque bancario", "18": "Pago contra reembolso",
                "19": "Pago mediante tarjeta"
            }
            payment_means = payment_means_map.get(payment_means_code, payment_means_code)

            iban = (payment.findtext(".//AccountToBeCredited/IBAN", default="") or "").strip()

            payment_details = {
                "due_date": due_date,
                "amount": (payment.findtext("InstallmentAmount", default="") or "").strip(),
                "means": payment_means,
                "means_code": payment_means_code,
                "iban": iban
            }

    items = []
    if invoice_element is not None:
        for line in invoice_element.findall(".//Items/InvoiceLine"):
            description = line.findtext("ItemDescription", default="N/A")
            quantity = line.findtext("Quantity", default="N/A")
            unit_price = line.findtext("UnitPriceWithoutTax", default="N/A")
            total_cost = line.findtext("TotalCost", default="N/A")

            obs = (line.findtext("AdditionalLineItemInformation", default="") or "").strip()
            lp = line.find("LineItemPeriod")
            periodo_linea = ""
            if lp is not None:
                lp_start = (lp.findtext("StartDate", default="") or "")
                lp_end = (lp.findtext("EndDate", default="") or "")
                try:
                    lp_start_f = datetime.strptime(lp_start, "%Y-%m-%d").strftime("%d/%m/%Y") if lp_start else ""
                    lp_end_f = datetime.strptime(lp_end, "%Y-%m-%d").strftime("%d/%m/%Y") if lp_end else ""
                    if lp_start_f or lp_end_f:
                        periodo_linea = f"{lp_start_f}–{lp_end_f}"
                except Exception:
                    periodo_linea = f"{lp_start}–{lp_end}"

            # Cargos y Descuentos a nivel de línea
            line_charges = []
            for c in line.findall(".//Charges/Charge"):
                line_charges.append({
                    "reason": (c.findtext("ChargeReason", default="") or "Cargo").strip(),
                    "amount": (c.findtext("ChargeAmount", default="0") or "0").strip()
                })
            
            line_discounts = []
            for d in line.findall(".//Discounts/Discount"):
                line_discounts.append({
                    "reason": (d.findtext("DiscountReason", default="") or "Dcto.").strip(),
                    "amount": (d.findtext("DiscountAmount", default="0") or "0").strip()
                })

            items.append({
                "Descripción": description,
                "Cantidad": quantity,
                "Precio Unitario": unit_price,
                "Importe": total_cost,
                "Observaciones": obs,
                "Periodo": periodo_linea,
                "Cargos": line_charges,
                "Descuentos": line_discounts
            })

    data = {
        "Número de Factura": invoice_number,
        "Fecha": issue_date,
        "Tipo Dcomento": invoice_type,
        "Moneda": invoice_currency,
        "Clase Factura": invoice_class_desc,
        "PeriodoFactura": invoicing_period,
        "Total Factura": totals.get("InvoiceTotal", "N/A"),
        "Totales": totals,
        "Emisor": emitter,
        "Receptor": receptor,
        "Tercero": tercero,
        "Conceptos": items,
        "Firma": _extract_signature_info_from_xml(xml_root),
        "InfoAdicional": invoice_additional_info,
        "ReferenciasLegales": legal_references,
        "TaxesWithheldDetails": taxes_withheld_details,
        "TaxesOutputDetails": taxes_output_details,
        "PaymentDetails": payment_details
    }
    return data


def _add_header(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.pagesize[1] - 20, "")
    canvas.restoreState()


def _add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    text = "REPRESENTACIÓN DEL CONTENIDO DE LA FACTURA ELECTRÓNICA Y DEL REGISTRO CONTABLE DE FACTURAS."
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    canvas.drawString(doc.leftMargin, 20, text)
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 20, f"{timestamp}")
    canvas.restoreState()


def _generate_pdf_from_invoice(invoice: dict, parametros: dict) -> io.BytesIO:
    buffer = io.BytesIO()

    # ---- Documento con 2 frames: cuerpo (arriba) + footer (abajo) ----
    left_margin = 30
    right_margin = 30
    top_margin = 30
    bottom_margin = 18

    footer_height = 5.8 * cm   # ajusta si lo necesitas
    gap = 0.25 * cm            # separación visual

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left_margin, rightMargin=right_margin,
        topMargin=top_margin, bottomMargin=bottom_margin
    )

    page_width, page_height = A4
    usable_width = page_width - left_margin - right_margin
    usable_height = page_height - top_margin - bottom_margin

    body_frame = Frame(
        x1=left_margin,
        y1=bottom_margin + footer_height + gap,
        width=usable_width,
        height=usable_height - footer_height - gap,
        id='body'
    )
    footer_frame = Frame(
        x1=left_margin,
        y1=bottom_margin,
        width=usable_width,
        height=footer_height,
        id='footer'
    )

    doc.addPageTemplates([
        PageTemplate(id='with_footer', frames=[body_frame, footer_frame],
                     onPage=lambda c, d: (_add_header(c, d), _add_footer(c, d)))
    ])

    # ---- Estilos ----
    elements = []
    styles = getSampleStyleSheet()
    styleH = styles['Heading1']
    styleN = styles['Normal']
    styleN.fontSize = 8
    styleN.leading = 10

    table_cell_style = ParagraphStyle('table_cell_style', parent=styles['Normal'], fontSize=8, leading=10)
    header_cell_style = ParagraphStyle('header_cell_style', parent=styles['Normal'], fontSize=8, leading=10, alignment=1)
    right_align_style = ParagraphStyle(name='RightAlign', parent=table_cell_style, alignment=TA_RIGHT)
    green_fill = colors.Color(red=0.88, green=0.94, blue=0.88)

    styleH_green = ParagraphStyle(
        name="Heading1Green",
        parent=styleH,
        textColor=colors.HexColor("#006400")  # verde oscuro
    )

    # ====== BLOQUE 1: Cabecera/resumen ======
    titulo = Paragraph("Resumen de Factura", styleH_green)
    info_factura = Paragraph(
        f"<b>Fecha de Emisión:</b> {invoice.get('Fecha', 'N/A')} "
        f"<b>Número:</b> {invoice.get('Número de Factura', 'N/A')}<br/>"
        f"<b>Clase de factura:</b> {invoice.get('Clase Factura', 'N/A')} "
        f"<b>Moneda:</b> {invoice.get('Moneda', 'N/A')}<br/>"
        f"<b>Periodo de facturación:</b> "
        f"{(invoice.get('PeriodoFactura', {}) or {}).get('Inicio', 'N/A')} – "
        f"{(invoice.get('PeriodoFactura', {}) or {}).get('Fin', 'N/A')}",
        styleN
    )
    info_extra = Paragraph(
        f"<b>Num. RCF:</b> {parametros['num_rcf']}<br/>"
        f"<b>Fecha y hora RCF:</b> {parametros['fecha_hora_registro']}<br/><br/>"
        f"<b>Num.Registro:</b> {parametros['num_registro']}<br/>"
        f"<b>Fecha y hora Registro:</b> {parametros['tipo_registro']}<br/>",
        styleN
    )
    table_info = Table([[[titulo, info_factura], info_extra]], colWidths=[doc.width * 0.6, doc.width * 0.4])
    table_info.setStyle(TableStyle([
        ('BOX', (1, 0), (1, 0), 1, colors.black),
        ('INNERGRID', (1, 0), (1, 0), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(table_info)
    elements.append(Spacer(1, 12))

    # ====== BLOQUE 2: Emisor/Receptor ======
    emisor = invoice.get("Emisor", {})
    receptor = invoice.get("Receptor", {})
    receptor_info = (
        f"<b>Nombre:</b> {receptor.get('Nombre', 'N/A')}<br/>"
        f"<b>NIF:</b> {receptor.get('NIF', 'N/A')}<br/>"
        f"<b>Dirección:</b> {receptor.get('Dirección', 'N/A')}<br/>"
        f"<b>Ofi.Cont.:</b> {receptor.get('OfiCont', 'N/A')}<br/>"
        f"<b>Org.Gest:</b> {receptor.get('OrgGest', 'N/A')}<br/>"
        f"<b>Und.Tram:</b> {receptor.get('UndTram', 'N/A')}"
    )
    data_parties = [
        [Paragraph("<b>EMISOR</b>", styleN), Paragraph("<b>RECEPTOR</b>", styleN)],
        [Paragraph(
            f"<b>Nombre:</b> {emisor.get('Nombre', 'N/A')}<br/>"
            f"<b>NIF:</b> {emisor.get('NIF', 'N/A')}<br/>"
            f"<b>Dirección:</b> {emisor.get('Dirección', 'N/A')}<br/>"
            f"<b>Poblacion:</b> {emisor.get('Poblacion', 'N/A')}<br/>"
            f"<b>Cod.Postal:</b> {emisor.get('Cod.Postal', 'N/A')}<br/>"
            f"<b>Provincia:</b> {emisor.get('Provincia', 'N/A')}", styleN
        ),
         Paragraph(receptor_info, styleN)]
    ]
    table_parties = Table(data_parties, colWidths=[doc.width/2.0, doc.width/2.0])
    table_parties.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), green_fill),
    ]))
    elements.append(table_parties)
    elements.append(Spacer(1, 12))

    # ====== BLOQUE 3: Ítems ======
    items = invoice.get("Conceptos", [])
    if items:
        data_table = [[
            Paragraph("Descripción", header_cell_style),
            Paragraph("Cantidad", header_cell_style),
            Paragraph("Precio Unitario", header_cell_style),
            Paragraph("Importe", header_cell_style)
        ]]
        for item in items:
            def _fmt(val, fmt):
                try:
                    return fmt.format(float(val))
                except Exception:
                    return val if val is not None else "N/A"

            obs_text = (item.get("Observaciones", "") or "").strip()
            periodo_text = (item.get("Periodo", "") or "").strip()

            desc_text = item.get("Descripción", "N/A") or "N/A"
            extra_lines = []
            if obs_text:
                extra_lines.append(f"({obs_text})")
            if periodo_text:
                extra_lines.append(f"(Periodo: {periodo_text})")
            
            if extra_lines:
                desc_text = desc_text + "\n" + "\n".join(extra_lines)

            data_table.append([
                Paragraph(desc_text, table_cell_style),
                Paragraph(_fmt(item.get("Cantidad", 0), "{:.2f}"), right_align_style),
                Paragraph(_fmt(item.get("Precio Unitario", 0), "{:.4f}"), right_align_style),
                Paragraph(_fmt(item.get("Importe", 0), "{:.2f}"), right_align_style),
            ])

        col_widths = [doc.width * 0.60, doc.width * 0.12, doc.width * 0.14, doc.width * 0.14]
        table_items = Table(data_table, colWidths=col_widths)
        table_items.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), green_fill),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ]))
        elements.append(table_items)
        elements.append(Spacer(1, 12))

        # ====== BLOQUE 3.1: CARGOS (Nueva tabla separada) ======
        all_charges = []
        for itm in items:
            all_charges.extend(itm.get("Cargos", []))
        
        if all_charges:
            elements.append(Paragraph("<u><b><i>CARGOS</i></b></u>", styleN))
            elements.append(Spacer(1, 4))
            
            charge_data = [[
                Paragraph("CONCEPTO", header_cell_style),
                Paragraph("TIPO (%)", header_cell_style),
                Paragraph("IMPORTE", header_cell_style)
            ]]
            for c in all_charges:
                charge_data.append([
                    Paragraph(c['reason'], table_cell_style),
                    Paragraph("-", header_cell_style),
                    Paragraph(_fmt(c.get('amount', 0), "{:.2f}"), right_align_style)
                ])
            
            c_col_widths = [doc.width * 0.70, doc.width * 0.15, doc.width * 0.15]
            table_charges = Table(charge_data, colWidths=c_col_widths)
            table_charges.setStyle(TableStyle([
                ('BOX', (0,0), (-1,-1), 1, colors.black),
                ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('BACKGROUND', (0,0), (-1,0), green_fill),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            elements.append(table_charges)
            elements.append(Spacer(1, 12))
    else:
        elements.append(Paragraph("No hay conceptos en la factura.", styleN))
        elements.append(Spacer(1, 12))

    # ====== BLOQUE 3b: Desglose de IVA (si hay múltiples tipos) ======
    taxes_output_details = invoice.get("TaxesOutputDetails", []) or []
    TAX_TYPE_MAP = {"01": "IVA", "02": "IGIC", "03": "IPSI", "04": "IRPF", "05": "Otros"}

    # Filtramos para ver si hay algún importe distinto de cero
    has_tax_amounts = False
    for t in taxes_output_details:
        try:
            if float(t.get("amount", 0) or 0) != 0:
                has_tax_amounts = True
                break
        except Exception:
            continue

    if len(taxes_output_details) > 0 and has_tax_amounts:
        elements.append(Paragraph("<b>Desglose de Impuestos</b>", styleN))
        elements.append(Spacer(1, 4))

        tax_header = [
            Paragraph("Tipo", header_cell_style),
            Paragraph("% Tipo", header_cell_style),
            Paragraph("Base Imponible", header_cell_style),
            Paragraph("Cuota", header_cell_style),
            Paragraph("% Rec.Eq.", header_cell_style),
            Paragraph("Rec.Eq.", header_cell_style),
        ]
        tax_data = [tax_header]

        for t in taxes_output_details:
            tipo = TAX_TYPE_MAP.get(t.get("type_code", "01"), "IVA")
            rate = t.get("rate", "0")
            base = t.get("base", "0")
            amount = t.get("amount", "0")
            surcharge = t.get("surcharge", "0")
            surcharge_amt = t.get("surcharge_amount", "0")

            def _fmt_num(val, decimals=2):
                try:
                    return f"{float(val):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
                except Exception:
                    return val or "0"

            tax_data.append([
                Paragraph(tipo, table_cell_style),
                Paragraph(_fmt_num(rate, 2), right_align_style),
                Paragraph(_fmt_num(base, 2), right_align_style),
                Paragraph(_fmt_num(amount, 2), right_align_style),
                Paragraph(_fmt_num(surcharge, 2), right_align_style),
                Paragraph(_fmt_num(surcharge_amt, 2), right_align_style),
            ])

        tax_col_widths = [doc.width * 0.12, doc.width * 0.12, doc.width * 0.22, doc.width * 0.18, doc.width * 0.16, doc.width * 0.20]
        tax_table = Table(tax_data, colWidths=tax_col_widths)
        tax_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), green_fill),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ]))
        elements.append(tax_table)
        elements.append(Spacer(1, 8))

    # ====== BLOQUE 3c: Forma de Pago ======
    payment_info = invoice.get("PaymentDetails", {}) or {}
    if payment_info and (payment_info.get("iban") or payment_info.get("due_date")):
        elements.append(Paragraph("<b>Forma de Pago</b>", styleN))
        elements.append(Spacer(1, 4))

        payment_text_parts = []
        if payment_info.get("means"):
            payment_text_parts.append(f"<b>Medio:</b> {payment_info['means']}")
        if payment_info.get("due_date"):
            payment_text_parts.append(f"<b>Vencimiento:</b> {payment_info['due_date']}")
        if payment_info.get("amount"):
            payment_text_parts.append(f"<b>Importe:</b> {payment_info['amount']} €")
        if payment_info.get("iban"):
            payment_text_parts.append(f"<b>IBAN:</b> {payment_info['iban']}")

        payment_paragraph = Paragraph(" &nbsp;|&nbsp; ".join(payment_text_parts), styleN)
        elements.append(payment_paragraph)
        elements.append(Spacer(1, 8))

    # ====== BLOQUE 4+5 (FOOTER): Totales y Firma ======
    # Forzamos salto al frame del pie
    elements.append(FrameBreak())

    # -- Totales --
    totals = invoice.get("Totales", {})
    if totals:
        def V(key, default="N/A"):
            return totals.get(key, default)

        withheld_details = invoice.get("TaxesWithheldDetails", []) or []
        TAX_WITHHELD_MAP = {"04": "IRPF", "01": "IVA", "02": "IGIC", "03": "IPSI"}

        def _fmt_rate(x: str) -> str:
            try:
                val = float(str(x).replace(",", "."))
                s = f"{val:.2f}"
                return s.rstrip("0").rstrip(".")
            except Exception:
                return (x or "").strip()

        if withheld_details:
            parts = []
            for d in withheld_details:
                code = (d.get("code") or "").strip()
                rate = _fmt_rate(d.get("rate", ""))
                label_name = TAX_WITHHELD_MAP.get(code, "Otros")
                parts.append(f"Retención ({rate} %) {label_name}")
            ret_label_text = " · ".join(parts) + ":"
        else:
            ret_label_text = "Retenciones:"

        half = doc.width / 2.0
        left_data = [
            [Paragraph("<b>Importe bruto total:</b>", styleN), Paragraph(V("TotalGrossAmount"), right_align_style)],
            [Paragraph("<b>Descuentos generales:</b>", styleN), Paragraph(V("TotalGeneralDiscounts"), right_align_style)],
            [Paragraph(f"<b>{ret_label_text}</b>", styleN), Paragraph(V("TotalTaxesWithheld"), right_align_style)],
        ]
        right_data = [
            [Paragraph("<b>Base imponible antes de impuestos:</b>", styleN), Paragraph(V("TotalGrossAmountBeforeTaxes"), right_align_style)],
            [Paragraph("<b>Importe de impuestos:</b>", styleN), Paragraph(V("TotalTaxOutputs"), right_align_style)],
            [Paragraph("<b>Importe total factura:</b>", styleN), Paragraph(V("InvoiceTotal"), right_align_style)],
        ]
        left_table = Table(left_data, colWidths=[half * 0.70, half * 0.30])
        left_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), green_fill),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        right_table = Table(right_data, colWidths=[half * 0.70, half * 0.30])
        right_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), green_fill),
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
        elements.append(KeepTogether([totals_table]))
        elements.append(Spacer(1, 6))

    # -- Firma electrónica --
    firma = invoice.get("Firma", {})
    if firma and firma.get("estado", "").startswith("Firma"):
        styleN_firma = ParagraphStyle(name='NormalFirma', parent=styleN, fontSize=7, leading=9)
        style_subtitle = ParagraphStyle(name='SubtitleCentered', parent=getSampleStyleSheet()['Heading2'], alignment=1)

        elements.append(Paragraph("Firma electrónica", style_subtitle))

        firma_data = [
            [
                Paragraph("<b>Firmante:</b>", styleN_firma), Paragraph(firma.get("firmante", "N/A"), styleN_firma),
                Paragraph("<b>NIF:</b>", styleN_firma), Paragraph(firma.get("nif", "N/A"), styleN_firma),
                Paragraph("<b>Algoritmo:</b>", styleN_firma), Paragraph(firma.get("algoritmo", "N/A"), styleN_firma)
            ],
            [
                Paragraph("<b>Fecha Firma:</b>", styleN_firma), Paragraph(firma.get("fecha_firma", "N/A"), styleN_firma),
                Paragraph("<b>Desde:</b>", styleN_firma), Paragraph(firma.get("valido_desde", "N/A"), styleN_firma),
                Paragraph("<b>Hasta:</b>", styleN_firma), Paragraph(firma.get("valido_hasta", "N/A"), styleN_firma)
            ],
            [
                Paragraph("<b>Estado actual:</b>", styleN_firma), Paragraph(firma.get("estado_certificado", "N/A"), styleN_firma),
                Paragraph("<b>Validez en firma:</b>", styleN_firma), Paragraph(firma.get("validez_en_firma", "N/A"), styleN_firma),
                Paragraph("<b>Autoridad Certificación:</b>", styleN_firma), Paragraph(firma.get("autoridad_certificadora", "N/A"), styleN_firma)
            ]
        ]
        col_widths = [
            doc.width * 0.11, doc.width * 0.37,
            doc.width * 0.09, doc.width * 0.16,
            doc.width * 0.10, doc.width * 0.17
        ]
        table_firma = Table(firma_data, colWidths=col_widths)
        table_firma.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), green_fill),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        elements.append(KeepTogether([table_firma]))

    # ---- Build ----
    doc.build(elements)
    buffer.seek(0)
    return buffer


# ------------------------------
# API pública del módulo
# ------------------------------

def render_pdf_from_xsig(
    xsig_file: BinaryIO,
    *,
    num_registro: str,
    tipo_registro: str,
    num_rcf: str,
    fecha_hora_registro: datetime,
    timezone: str = "Europe/Madrid",
) -> io.BytesIO:
    """
    Devuelve un BytesIO con el PDF generado a partir del XSIG y los campos auxiliares.
    No escribe a disco.
    """
    xsig_bytes = xsig_file.read()
    if not xsig_bytes:
        raise ValueError("Archivo vacío o no legible.")

    xml_bytes = _extract_xml_from_xsig_bytes(xsig_bytes)
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        raise ValueError(f"El archivo no parece un XSIG/XML válido: {e}")

    invoice_data = _extract_invoice_data_from_xml(root)

    params = {
        "num_registro": num_registro,
        "tipo_registro": tipo_registro,
        "num_rcf": num_rcf,
        "fecha_hora_registro": fecha_hora_registro.strftime("%d/%m/%Y %H:%M"),
    }

    pdf_buffer = _generate_pdf_from_invoice(invoice_data, params)
    pdf_buffer.seek(0)
    return pdf_buffer
