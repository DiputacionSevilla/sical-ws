# api/main.py
import os, sys, io, time, uuid, logging
from datetime import datetime
from typing import Optional, List, Dict, Any

# --- Hacer que 'core' sea importable ejecutando como script ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from core.service import (
    generar_informe_conformidad_pdf_desde_payload,
    generar_pdf_desde_xsig,
)
from core.factura_pdf import generate_resumen_factura_pdf

# --- NUEVO: import del generador de PDF de datos de factura (JSON) ---
try:
    from core.datosfactura_pdf import build_pdf as build_datosfactura_pdf
except Exception as e:
    # No abortamos el arranque, pero lo dejaremos claro en el log.
    build_datosfactura_pdf = None
    logging.getLogger("api-conformidad").warning(
        f"No se pudo importar core.datosfactura_pdf.build_pdf: {e}"
    )

# -------------------------------------------------------------------
# LOGGING BÁSICO + REQUEST ID
# -------------------------------------------------------------------
logger = logging.getLogger("api-conformidad")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

app = FastAPI(
    title="Informes Diputación de Sevilla",
    version="1.2.0",
    description=(
        "Webservice para generar Informe de (No) Conformidad, convertir XSIG/XML a PDF, "
        "resumen de factura y datos de factura (JSON) sin BBDD."
    ),
)

# CORS (endurecer en producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Middleware para trazabilidad y métricas simples
# -------------------------------------------------------------------
@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    logger.info(f"[{req_id}] IN  {request.client.host} {request.method} {request.url.path}")
    try:
        response = await call_next(request)
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.exception(f"[{req_id}] EXC {request.method} {request.url.path} after={elapsed_ms}ms err={e}")
        raise
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(f"[{req_id}] OUT {request.method} {request.url.path} status={response.status_code} after={elapsed_ms}ms")
    response.headers["X-Request-ID"] = req_id
    return response

@app.get("/health", tags=["misc"])
def health():
    return {"status": "ok"}

# ---------- MODELOS (Pydantic v2) para /api/informe ----------
class Aplicacion(BaseModel):
    org: str = ""
    fun: str = ""
    eco: str = ""

    model_config = {
        "json_schema_extra": {"example": {"org": "1200", "fun": "1510", "eco": "226.06"}}
    }

class InformeWSPayload(BaseModel):
    # Registro
    punto_entrada: str = ""
    id_punto_entrada: str = ""
    fecha_hora_entrada: str = ""  # Se imprime tal cual en el PDF
    num_rcf: str = Field(..., description="Número RCF")

    # Datos factura
    proveedor: str = ""
    nif_proveedor: str = ""
    fecha_expedicion: str = ""
    vfacnum: str = ""
    importe_total: str = ""
    concepto: str = ""

    # Área
    area_code: Optional[str] = Field(
        default=None,
        description="Código de área (ej. '01'). Si no envías area_name, intentará mapearlo por CSV."
    )
    area_name: Optional[str] = Field(
        default=None,
        description="Nombre de área. Opcional si envías area_code y existe en CSV."
    )
    unidad: Optional[str] = ""

    # Aplicaciones y expediente
    expediente_contrato: Optional[str] = ""
    aplicaciones: List[Aplicacion] = Field(default_factory=list)
    apps_single_row: bool = True

    # Observaciones opcional
    observaciones: Optional[str] = ""

    # Conformidad
    resultado_conformidad: str = Field(
        default="conforme",
        pattern="^(conforme|no_conforme)$",
        description="Indica si es conforme o no_conforme"
    )
    motivo_no_conformidad: Optional[str] = None

    # CSV de áreas
    areas_csv_path: str = Field(default="areas.csv", description="Ruta al CSV de áreas (opcional)")

    @field_validator("motivo_no_conformidad")
    @classmethod
    def _motivo_required_when_no_conforme(cls, v, info):
        values = info.data
        if values.get("resultado_conformidad") == "no_conforme":
            if not (v or "").strip():
                raise ValueError("motivo_no_conformidad es obligatorio cuando resultado_conformidad = 'no_conforme'")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "punto_entrada": "FACe",
                "id_punto_entrada": "FACe-123456",
                "fecha_hora_entrada": "16/10/2025 10:45",
                "num_rcf": "2025-0001",
                "proveedor": "Proveedor Ejemplo S.A.",
                "nif_proveedor": "A12345678",
                "fecha_expedicion": "15/10/2025",
                "vfacnum": "F-2025-7788",
                "importe_total": "1.234,56 €",
                "concepto": "Suministro de material informático",
                "area_code": "01",
                "area_name": "Área de Hacienda",
                "unidad": "Servicio de Contratación",
                "expediente_contrato": "EXP-2025-00999",
                "aplicaciones": [
                    {"org": "1200", "fun": "1510", "eco": "226.06"},
                    {"org": "1200", "fun": "1510", "eco": "227.99"}
                ],
                "apps_single_row": True,
                "observaciones": "texto libre a mostrar al final del informe",
                "resultado_conformidad": "conforme",
                "motivo_no_conformidad": None,
                "areas_csv_path": "areas.csv"
            }
        }
    }

# ---- Modelos para /api/factura ----
class PeriodoModel(BaseModel):
    inicio: Optional[str] = None
    fin: Optional[str] = None

class FacturaCabeceraModel(BaseModel):
    numero: str
    fecha: str
    moneda: Optional[str] = "EUR"
    clase: Optional[str] = "Original"
    periodo: Optional[PeriodoModel] = None

class RegistroModel(BaseModel):
    num_rcf: Optional[str] = None
    fecha_hora_registro: Optional[str] = None
    num_registro: Optional[str] = None
    tipo_registro: Optional[str] = None

class ParteModel(BaseModel):
    Nombre: Optional[str] = None
    NIF: Optional[str] = None
    Dirección: Optional[str] = None
    Poblacion: Optional[str] = None
    Cod_Postal: Optional[str] = Field(None, alias="Cod.Postal")
    Provincia: Optional[str] = None
    OfiCont: Optional[str] = None
    OrgGest: Optional[str] = None
    UndTram: Optional[str] = None

class TotalesModel(BaseModel):
    TotalGrossAmount: Optional[str] = None
    TotalGeneralDiscounts: Optional[str] = None
    TotalGrossAmountBeforeTaxes: Optional[str] = None
    TotalTaxOutputs: Optional[str] = None
    TotalTaxesWithheld: Optional[str] = None
    InvoiceTotal: Optional[str] = None
    TotalOutstandingAmount: Optional[str] = None
    TotalExecutableAmount: Optional[str] = None

class FacturaResumenPayload(BaseModel):
    factura: FacturaCabeceraModel
    registro: RegistroModel
    emisor: ParteModel
    receptor: Optional[ParteModel] = None
    texto1: Optional[str] = ""
    totales: Optional[TotalesModel] = None
    filename: Optional[str] = Field(default=None, description="Nombre de descarga opcional (sin rutas)")

# -------------------------------------------------------------------
# NUEVOS MODELOS: /api/datosfactura (100% JSON, sin Oracle)
# -------------------------------------------------------------------
class GeneralesIn(BaseModel):
    # Identificadores y fechas de registro (FACe/SIDERAL)
    nfacreg: str
    numregistroface: Optional[str] = None
    fecharegistroface: Optional[str] = None
    nregnum: Optional[str] = None
    freggen: Optional[str] = None

    # Terceros
    vtercod: Optional[str] = None
    proveedor: Optional[str] = None
    endosatario: Optional[str] = None
    endosatario_nombre: Optional[str] = None

    # Factura
    vfacnum: Optional[str] = None
    ffactur: Optional[str] = None

    # Resolución
    respropia: Optional[str] = Field(default=None, pattern="^[sSnN]$")
    nresnum: Optional[str] = None
    fresol: Optional[str] = None
    textosinres: Optional[str] = None

    # Expediente/Concepto
    expnorma: Optional[str] = None
    vtexto1: Optional[str] = None

    # Totales
    nbasimp: Optional[float] = None
    nfaciva: Optional[float] = None
    descuento: Optional[float] = None
    nfacimp: Optional[float] = None

    # Overrides opcionales de display
    num_registro_display: Optional[str] = None
    fecha_registro_display: Optional[str] = None

    # Logo / área
    area_code: Optional[str] = None
    logo_path: Optional[str] = None

class AplicacionIn(BaseModel):
    organica: str
    funcional: str
    economica: str
    referencia: Optional[str] = None
    cuenta: Optional[str] = None
    importe: float

class DescuentoIn(BaseModel):
    anio: Optional[str] = None
    naturaleza: Optional[str] = None
    aplicacion: Optional[str] = None
    base_imponible: Optional[float] = 0.0
    porcentaje: Optional[float] = None
    importe: Optional[float] = 0.0
    cuenta: Optional[str] = None

class DatosFacturaPayload(BaseModel):
    generales: GeneralesIn
    aplicaciones: List[AplicacionIn] = []
    descuentos: List[DescuentoIn] = []

# -------------------------------------------------------------------
# Utilidades locales (formato € y fechas)
# -------------------------------------------------------------------
def _fmt_eur(val) -> str:
    try:
        f = float(val or 0.0)
        s = f"{f:,.2f} €"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00 €"

def _safe_date_str(d: Optional[str]) -> str:
    if not d:
        return ""
    d = d.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(d, fmt)
            return dt.strftime("%d/%m/%Y")
        except Exception:
            continue
    return d

def _safe_dt_str(d: Optional[str]) -> str:
    if not d:
        return ""
    d = d.strip()
    for fmt_in, fmt_out in [
        ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"),
        ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"),
        ("%Y-%m-%d", "%d/%m/%Y"),
        ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"),
        ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M"),
        ("%d/%m/%Y", "%d/%m/%Y"),
    ]:
        try:
            dt = datetime.strptime(d, fmt_in)
            return dt.strftime(fmt_out)
        except Exception:
            continue
    return d

def _normalize_generales(g: GeneralesIn) -> dict:
    # Displays de registro (si no vienen, los calculamos)
    if g.num_registro_display and g.fecha_registro_display:
        num_reg_disp = g.num_registro_display
        fec_reg_disp = g.fecha_registro_display
    else:
        if (g.numregistroface or "").strip():
            num_reg = (g.numregistroface or "").strip()
            fec_reg = _safe_dt_str(g.fecharegistroface)
            num_reg_disp = f"{num_reg} (FACe)" if num_reg else "(FACe)"
            fec_reg_disp = f"{fec_reg} (FACe)" if fec_reg else "(FACe)"
        else:
            year_suffix = ""
            try:
                y = None
                if g.freggen:
                    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
                        try:
                            y = datetime.strptime(g.freggen, fmt).year
                            break
                        except Exception:
                            continue
                year_suffix = f"/{y}" if y else ""
            except Exception:
                year_suffix = ""
            nro = (g.nregnum or "").strip()
            num_reg = f"{nro}{year_suffix}" if nro else ""
            fec_reg = _safe_dt_str(g.freggen)
            num_reg_disp = f"{num_reg} (SIDERAL)" if num_reg else "(SIDERAL)"
            fec_reg_disp = f"{fec_reg} (SIDERAL)" if fec_reg else "(SIDERAL)"

    if (g.respropia or "").upper() == "S":
        resol = f"{(g.nresnum or '').strip()} ({_safe_date_str(g.fresol)})"
    else:
        resol = (g.textosinres or "").strip()

    generales = {
        "nfacreg": g.nfacreg,
        "num_registro_display": num_reg_disp,
        "fecha_registro_display": fec_reg_disp,
        "tercero_codigo": g.vtercod or "",
        "tercero_nombre": g.proveedor or "",
        "endosatario_codigo": g.endosatario or "",
        "endosatario_nombre": g.endosatario_nombre or "",
        "num_factura_proveedor": g.vfacnum or "",
        "fecha_factura": _safe_date_str(g.ffactur),
        "resolucion": resol,
        "expediente": g.expnorma or "",
        "concepto": g.vtexto1 or "",
        # Totales (según tu decisión reciente)
        "importe_total": _fmt_eur(g.nbasimp),
        "iva": _fmt_eur(g.nfaciva),
        "descuento": _fmt_eur(g.descuento),
        "importe_liquido": _fmt_eur(g.nfacimp),
    }
    return generales

def _normalize_aplicaciones(apl_in: List[AplicacionIn]) -> List[dict]:
    out = []
    for a in apl_in:
        out.append({
            "organica": a.organica,
            "funcional": a.funcional,
            "economica": a.economica,
            "referencia": a.referencia or "",
            "cuenta": a.cuenta or "",
            "importe": a.importe,
            "importe_fmt": _fmt_eur(a.importe),
        })
    return out

def _normalize_descuentos(dct_in: List[DescuentoIn]) -> List[dict]:
    out = []
    for d in dct_in:
        base = float(d.base_imponible or 0.0)
        imp = float(d.importe or 0.0)
        if d.porcentaje is None:
            porc = (imp / base * 100.0) if base else 0.0
        else:
            porc = float(d.porcentaje or 0.0)
        out.append({
            "anio": d.anio or "",
            "naturaleza": d.naturaleza or "",
            "aplicacion": d.aplicacion or "",
            "base_imponible": base,
            "porcentaje": porc,
            "importe": imp,
            "cuenta": d.cuenta or "",
            "base_imponible_fmt": _fmt_eur(base),
            "porcentaje_fmt": f"{porc:.2f} %",
            "importe_fmt": _fmt_eur(imp),
        })
    return out

# -------------------------------------------------------------------
# ENDPOINTS EXISTENTES
# -------------------------------------------------------------------
@app.post(
    "/api/informe",
    tags=["informe"],
    summary="Generar Informe de (No) Conformidad (sin BBDD)",
    responses={
        200: {"description": "PDF generado", "content": {"application/pdf": {}}},
        400: {"description": "Petición inválida (validación)"},
        500: {"description": "Error interno generando el PDF"},
    }
)
def api_generar_informe(req: InformeWSPayload):
    try:
        payload = req.model_dump()
        if payload.get("aplicaciones"):
            payload["aplicaciones"] = [
                {"org": a["org"], "fun": a["fun"], "eco": a["eco"]}
                for a in payload["aplicaciones"]
            ]
        pdf_bytes = generar_informe_conformidad_pdf_desde_payload(
            payload=payload,
            areas_csv_path=req.areas_csv_path,
        )
        filename = f"informe_{req.num_rcf}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        logger.warning(f"/api/informe bad request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"/api/informe internal error: {e}")
        raise HTTPException(status_code=500, detail=f"Error generando informe: {e}")

@app.post(
    "/api/xml2pdf",
    tags=["xml"],
    summary="Convertir factura XSIG/XML a PDF",
    responses={
        200: {"description": "PDF generado", "content": {"application/pdf": {}}},
        400: {"description": "Petición inválida"},
        500: {"description": "Error interno generando el PDF"},
    }
)
async def api_xml_a_pdf(
    file: UploadFile = File(..., description="Archivo XSIG o XML"),
    num_registro: str = Form(...),
    tipo_registro: str = Form(...),
    num_rcf: str = Form(...),
    fecha_registro: Optional[str] = Form(None, description="Fecha/hora ISO 8601 (opcional, ej. 2025-10-16T10:45:00)"),
    fecha_registro_date: Optional[str] = Form(None, description="YYYY-MM-DD (alternativa)"),
    hora_registro_time: Optional[str] = Form(None, description="HH:MM[:SS] (alternativa)"),
):
    try:
        xsig_bytes = await file.read()
        if not xsig_bytes:
            raise HTTPException(status_code=400, detail="Archivo vacío o ilegible.")

        dt_obj = None
        if fecha_registro:
            try:
                dt_obj = datetime.fromisoformat(fecha_registro)
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="fecha_registro debe estar en ISO 8601 (YYYY-MM-DDTHH:MM:SS)"
                )

        pdf_bytes = generar_pdf_desde_xsig(
            xsig_bytes=xsig_bytes,
            num_registro=num_registro.strip(),
            tipo_registro=tipo_registro.strip(),
            num_rcf=num_rcf.strip(),
            fecha_registro=dt_obj,
            fecha_registro_date=fecha_registro_date,
            hora_registro_time=hora_registro_time,
        )

        filename = f"Factura_{num_rcf or num_registro}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"/api/xml2pdf internal error: {e}")
        raise HTTPException(status_code=500, detail=f"Error generando PDF desde XML: {e}")

@app.post(
    "/api/factura",
    tags=["factura"],
    summary="Genera PDF resumen de factura desde datos JSON",
    responses={
        200: {"description": "PDF generado", "content": {"application/pdf": {}}},
        500: {"description": "Error interno generando el PDF"},
    }
)
def api_factura_resumen(payload: Dict[str, Any] | 'FacturaResumenPayload'):
    try:
        if isinstance(payload, dict):
            data = payload
        else:
            data = payload.model_dump(by_alias=True)
        pdf_bytes = generate_resumen_factura_pdf(data)
        numero = data.get("factura", {}).get("numero", "sin_numero")
        filename = data.get("filename") or f"Resumen_{numero}.pdf"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)
    except Exception as e:
        logger.exception(f"/api/factura internal error: {e}")
        raise HTTPException(status_code=500, detail=f"Error generando resumen de factura: {e}")

# -------------------------------------------------------------------
# NUEVO ENDPOINT: /api/datosfactura (JSON -> PDF, sin BBDD)
# -------------------------------------------------------------------
@app.post(
    "/api/datosfactura",
    tags=["datosfactura"],
    summary="Genera PDF de datos de factura desde JSON (sin Oracle)",
    responses={
        200: {"description": "PDF generado", "content": {"application/pdf": {}}},
        400: {"description": "Petición inválida"},
        500: {"description": "Error interno generando el PDF"},
    }
)
def api_datosfactura_json(payload: DatosFacturaPayload):
    if build_datosfactura_pdf is None:
        raise HTTPException(
            status_code=500,
            detail="El módulo core.datosfactura_pdf no está disponible."
        )
    try:
        g_norm = _normalize_generales(payload.generales)
        apl_norm = _normalize_aplicaciones(payload.aplicaciones)
        dct_norm = _normalize_descuentos(payload.descuentos)

        datos_pdf = {
            "generales": g_norm,
            "aplicaciones": apl_norm,
            "descuentos": dct_norm,
            "area_code": payload.generales.area_code or "",
            "logo_path": payload.generales.logo_path or ""
        }

        pdf_io = build_datosfactura_pdf(datos_pdf)
        filename = f"datos_factura_{payload.generales.nfacreg}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_io.getvalue()),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.exception("/api/datosfactura internal error")
        raise HTTPException(status_code=500, detail=f"Error generando PDF datos de factura: {e}")

# ---- Arranque programático en puerto 5050 (estable en Windows) ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5050,
        reload=False,
        workers=1
    )
