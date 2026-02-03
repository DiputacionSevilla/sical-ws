import os
import glob
from io import BytesIO
from typing import Iterable, Dict, Any, List, Tuple, Optional
from datetime import datetime, time

import pytz

from core.areas import cargar_diccionario_areas
from core.pdf import generate_acta_pdf
from core.xsig_pdf import render_pdf_from_xsig

TZ_MADRID = pytz.timezone("Europe/Madrid")


class InformeConformidadError(Exception):
    pass


def _normalize_area_code(area_code: Optional[str]) -> str:
    """
    Normaliza el código de área. Si es numérico, lo rellena a 2 dígitos (01, 02...).
    Si viene vacío o None, devuelve "".
    """
    if not area_code:
        return ""
    ac = str(area_code).strip()
    if ac.isdigit():
        return ac.zfill(2)
    return ac


def _find_logo_for_area(area_code: str) -> Optional[str]:
    """
    Busca 'images/logo_<area_code>.(png|jpg|jpeg|gif|bmp)'.
    Si no existe, prueba en raíz, assets/ y static/.
    """
    if not area_code:
        return None

    exts = ("png", "jpg", "jpeg", "gif", "bmp")
    search_roots = [
        "images",          # << prioridad
        ".",               # raíz del proyecto
        "assets",
        "static",
    ]

    for root in search_roots:
        for ext in exts:
            p = os.path.join(root, f"logo_{area_code}.{ext}")
            if os.path.isfile(p):
                return p
    return None


# ===========================================
#   Informe (SIN BBDD) desde payload JSON
# ===========================================
def generar_informe_conformidad_pdf_desde_payload(
    *,
    payload: Dict[str, Any],
    areas_csv_path: str = "areas.csv",
) -> bytes:
    """
    Genera el PDF del Informe (Conformidad / No conformidad) SIN acceder a BBDD.
    Usa los datos recibidos en 'payload'. Devuelve bytes del PDF.
    """
    # Área / logo
    areas_dict = cargar_diccionario_areas(areas_csv_path)
    area_code = _normalize_area_code(payload.get("area_code"))
    area_name = payload.get("area_name") or areas_dict.get(area_code) or (f"Área {area_code}" if area_code else "")
    area_logo = _find_logo_for_area(area_code) if area_code else None

    # Aplicaciones
    aplicaciones_in: Iterable[Dict[str, str]] = payload.get("aplicaciones") or []
    aplicaciones: List[Tuple[str, str, str]] = []
    for item in aplicaciones_in:
        org = (item.get("org") or item.get("vaplorg") or "").strip()
        fun = (item.get("fun") or item.get("vaplfun") or "").strip()
        eco = (item.get("eco") or item.get("vapleco") or item.get("vapleco") or "").strip()
        aplicaciones.append((org, fun, eco))

    # Conformidad
    resultado = payload.get("resultado_conformidad", "conforme")
    if resultado not in ("conforme", "no_conforme"):
        raise ValueError("resultado_conformidad debe ser 'conforme' o 'no_conforme'")
    if resultado == "no_conforme" and not (payload.get("motivo_no_conformidad") or "").strip():
        raise ValueError("motivo_no_conformidad es obligatorio cuando resultado_conformidad = 'no_conforme'")

    observaciones = (payload.get("observaciones") or "").strip()

    data = {
        # Registro de entrada
        "punto_entrada": payload.get("punto_entrada", ""),
        "id_punto_entrada": payload.get("id_punto_entrada", ""),
        "fecha_hora_entrada": payload.get("fecha_hora_entrada", ""),
        "num_rcf": payload.get("num_rcf", ""),

        # Datos factura
        "proveedor": payload.get("proveedor", ""),
        "nif_proveedor": payload.get("nif_proveedor", ""),
        "fecha_expedicion": payload.get("fecha_expedicion", ""),
        "vfacnum": payload.get("vfacnum", ""),
        "importe_total": payload.get("importe_total", ""),
        "concepto": payload.get("concepto", ""),

        # Área / unidad / logo
        "area_code": area_code,
        "area_name": area_name,
        "area_logo": area_logo,
        "area": area_name,
        "unidad": payload.get("unidad", "") or "",

        # Aplicaciones y expediente
        "aplicaciones": aplicaciones,
        "expediente_contrato": payload.get("expediente_contrato", "") or "",
        "apps_single_row": bool(payload.get("apps_single_row", True)),

        # Conformidad
        "resultado_conformidad": resultado,
        "motivo_no_conformidad": (payload.get("motivo_no_conformidad") or "").strip(),

        # Observaciones 
        "observaciones": observaciones,
    }

    pdf_io: BytesIO = generate_acta_pdf(data)
    return pdf_io.getvalue()


# ===========================================
#   3) XML/XSIG → PDF (acepta bytes + params)
# ===========================================
def generar_pdf_desde_xsig(
    *,
    xsig_bytes: bytes,
    num_registro: str,
    tipo_registro: str,
    num_rcf: str,
    fecha_registro: Optional[datetime] = None,
    fecha_registro_date: Optional[str] = None,  # "YYYY-MM-DD"
    hora_registro_time: Optional[str] = None,   # "HH:MM[:SS]"
) -> bytes:
    """
    Envuelve render_pdf_from_xsig aceptando bytes y varias formas de fecha/hora.
    """
    # Normalizar fecha/hora
    if fecha_registro is None:
        if fecha_registro_date:
            d = datetime.strptime(fecha_registro_date, "%Y-%m-%d").date()
        else:
            d = datetime.now(TZ_MADRID).date()
        if hora_registro_time:
            parts = hora_registro_time.split(":")
            if len(parts) == 2:
                h = datetime.strptime(hora_registro_time, "%H:%M").time()
            else:
                h = datetime.strptime(hora_registro_time, "%H:%M:%S").time()
        else:
            now = datetime.now(TZ_MADRID)
            h = time(now.hour, now.minute, now.second)
        fecha_registro = TZ_MADRID.localize(datetime.combine(d, h))
    else:
        if fecha_registro.tzinfo is None:
            fecha_registro = TZ_MADRID.localize(fecha_registro)
        else:
            fecha_registro = fecha_registro.astimezone(TZ_MADRID)

    bio = BytesIO(xsig_bytes)
    pdf_io: BytesIO = render_pdf_from_xsig(
        bio,
        num_registro=num_registro,
        tipo_registro=tipo_registro,
        num_rcf=num_rcf,
        fecha_hora_registro=fecha_registro,
        timezone="Europe/Madrid",
    )
    return pdf_io.getvalue()
