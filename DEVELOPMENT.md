# SICAL-WS - Guia de Desarrollo

> Documento de contexto para continuar el desarrollo con asistencia de IA.

## Resumen del Proyecto

**SICAL-WS** es una API REST desarrollada con FastAPI para la Diputacion de Sevilla que:

1. **Genera informes PDF** de conformidad/no conformidad de facturas
2. **Procesa facturas electronicas** en formato XSIG/XML (FACe - Factura Electronica de las Administraciones Publicas)
3. **Genera resumenes PDF** desde datos JSON

**Caracteristicas clave:**
- Sin base de datos (stateless)
- Sin interfaz web (API pura)
- Desplegable en Docker
- Soporte para firma electronica XAdES

---

## Arquitectura

```
sical-ws/
├── api/
│   ├── __init__.py
│   └── main.py              # FastAPI app, endpoints, modelos Pydantic
├── core/
│   ├── __init__.py
│   ├── areas.py             # Carga CSV de areas, busqueda de logos
│   ├── config.py            # Configuracion desde .env
│   ├── constants.py         # Constantes globales
│   ├── datosfactura_pdf.py  # Genera PDF de datos de factura (JSON)
│   ├── factura_pdf.py       # Genera PDF resumen de factura (JSON)
│   ├── logger.py            # Configuracion de logging
│   ├── pdf.py               # Genera PDF de informe conformidad
│   ├── service.py           # Orquestacion: conecta endpoints con generadores
│   ├── utils.py             # Utilidades generales
│   └── xsig_pdf.py          # Parsea XSIG/XML y genera PDF de factura
├── images/                  # Logos por area (logo_XX.png)
├── tests/                   # Tests con pytest
├── areas.csv                # Mapeo codigo_area -> nombre_area
├── Dockerfile
├── render.yaml              # Config para Render.com
└── requirements.txt
```

---

## Endpoints de la API

### GET /health
Health check simple.

**Respuesta:** `{"status": "ok"}`

---

### POST /api/informe
Genera PDF de Informe de Conformidad o No Conformidad.

**Content-Type:** `application/json`

**Modelo de entrada (InformeWSPayload):**
```python
{
    "punto_entrada": str,           # Ej: "FACe"
    "id_punto_entrada": str,
    "fecha_hora_entrada": str,
    "num_rcf": str,                 # REQUERIDO
    "proveedor": str,
    "nif_proveedor": str,
    "fecha_expedicion": str,
    "vfacnum": str,                 # Numero factura
    "importe_total": str,
    "concepto": str,
    "area_code": str,               # Codigo area (01, 02, etc.)
    "area_name": str,
    "unidad": str,
    "aplicaciones": [               # Aplicaciones presupuestarias
        {"org": str, "fun": str, "eco": str}
    ],
    "expediente_contrato": str,
    "resultado_conformidad": str,   # "conforme" | "no_conforme"
    "motivo_no_conformidad": str,   # Requerido si no_conforme
    "observaciones": str
}
```

**Respuesta:** PDF binario (application/pdf)

**Archivo principal:** `core/pdf.py` -> `generate_acta_pdf()`

---

### POST /api/xml2pdf
Convierte factura XSIG/XML de FACe a PDF representativo.

**Content-Type:** `multipart/form-data`

**Parametros:**
- `file`: Archivo XSIG o XML (REQUERIDO)
- `num_registro`: str (REQUERIDO)
- `tipo_registro`: str (REQUERIDO)
- `num_rcf`: str (REQUERIDO)
- `fecha_registro`: str (ISO 8601, opcional)
- `hora_registro`: str (HH:MM, opcional)

**Respuesta:** PDF binario

**Archivo principal:** `core/xsig_pdf.py` -> `render_pdf_from_xsig()`

---

### POST /api/factura
Genera PDF resumen de factura desde JSON.

**Content-Type:** `application/json`

**Archivo principal:** `core/factura_pdf.py` -> `generate_resumen_factura_pdf()`

---

### POST /api/datosfactura
Genera PDF con datos detallados de factura desde JSON.

**Content-Type:** `application/json`

**Archivo principal:** `core/datosfactura_pdf.py` -> `build_pdf()`

---

## Tecnologias y Dependencias

| Tecnologia | Version | Uso |
|------------|---------|-----|
| Python | 3.12+ | Runtime |
| FastAPI | 0.115.0 | Framework API |
| uvicorn | 0.30.0 | Servidor ASGI |
| reportlab | 4.2.0 | Generacion de PDFs |
| cryptography | 43.0.0 | Parseo de certificados X.509 |
| python-dateutil | 2.9.0 | Manejo de fechas |
| pytz | 2024.1 | Zonas horarias |
| pydantic | 2.x | Validacion de datos |

---

## Formato XSIG/XML Soportado

El archivo `core/xsig_pdf.py` parsea facturas en formato **Facturae v3.2.x** (estandar FACe).

### Estructura XML esperada:
```xml
<Facturae>
  <FileHeader>
    <SchemaVersion>3.2.2</SchemaVersion>
    <Batch>...</Batch>
  </FileHeader>
  <Parties>
    <SellerParty>...</SellerParty>   <!-- Emisor -->
    <BuyerParty>                      <!-- Receptor -->
      <AdministrativeCentres>...</AdministrativeCentres>
    </BuyerParty>
  </Parties>
  <Invoices>
    <Invoice>
      <InvoiceHeader>...</InvoiceHeader>
      <InvoiceIssueData>...</InvoiceIssueData>
      <TaxesOutputs>...</TaxesOutputs>      <!-- IVA repercutido -->
      <TaxesWithheld>...</TaxesWithheld>    <!-- Retenciones (IRPF) -->
      <InvoiceTotals>...</InvoiceTotals>
      <Items>
        <InvoiceLine>...</InvoiceLine>
      </Items>
      <PaymentDetails>...</PaymentDetails>  <!-- Forma de pago -->
    </Invoice>
  </Invoices>
  <ds:Signature>...</ds:Signature>          <!-- Firma XAdES -->
</Facturae>
```

### Campos extraidos:

| Campo | XPath | Notas |
|-------|-------|-------|
| Emisor nombre | `//SellerParty//CorporateName` | o Individual/Name |
| Emisor NIF | `//SellerParty//TaxIdentificationNumber` | |
| Emisor direccion | `//SellerParty//AddressInSpain` | o OverseasAddress |
| Receptor nombre | `//BuyerParty//CorporateName` | |
| Centros admin | `//BuyerParty//AdministrativeCentre` | RoleTypeCode: 01=OfiCont, 02=OrgGest, 03=UndTram |
| Numero factura | `//InvoiceNumber` | + InvoiceSeriesCode |
| Fecha emision | `//IssueDate` | Formato YYYY-MM-DD |
| Periodo facturacion | `//InvoicingPeriod` | StartDate, EndDate |
| Lineas factura | `//Items/InvoiceLine` | Description, Quantity, UnitPriceWithoutTax, TotalCost |
| IVA repercutido | `//TaxesOutputs/Tax` | TaxRate, TaxableBase, TaxAmount |
| Recargo equivalencia | `//EquivalenceSurcharge` | + EquivalenceSurchargeAmount |
| Retenciones | `//TaxesWithheld/Tax` | TaxTypeCode: 04=IRPF |
| Forma de pago | `//PaymentDetails/Installment` | PaymentMeans, InstallmentDueDate |
| IBAN | `//AccountToBeCredited/IBAN` | |
| Firma | `//ds:Signature//ds:X509Certificate` | Certificado X.509 en base64 |

### Codigos de forma de pago (PaymentMeans):
```python
{
    "01": "Al contado",
    "02": "Recibo domiciliado",
    "03": "Recibo",
    "04": "Transferencia",
    "05": "Letra aceptada",
    ...
}
```

### Codigos de impuesto (TaxTypeCode):
```python
{
    "01": "IVA",
    "02": "IGIC",
    "03": "IPSI",
    "04": "IRPF"
}
```

---

## Generacion de PDFs

Todos los PDFs se generan con **ReportLab**. Patron comun:

```python
from reportlab.platypus import BaseDocTemplate, Table, Paragraph
from reportlab.lib.pagesizes import A4

def generate_pdf(data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, ...)

    elements = []
    # Construir elementos: Paragraph, Table, Spacer, etc.
    elements.append(Table(...))

    doc.build(elements)
    buffer.seek(0)
    return buffer
```

### Estilos comunes:
- `getSampleStyleSheet()` para estilos base
- `ParagraphStyle` para estilos personalizados
- `TableStyle` para formato de tablas
- Color verde corporativo: `colors.Color(red=0.88, green=0.94, blue=0.88)`

---

## Ejecucion Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar servidor de desarrollo
uvicorn api.main:app --reload --port 8000

# Ejecutar tests
pytest tests/
```

---

## Docker

```bash
# Construir imagen
docker build -t sical-ws .

# Ejecutar contenedor
docker run -d -p 8000:8000 sical-ws

# Ver logs
docker logs -f <container_id>
```

---

## Convenciones de Codigo

1. **Type hints** en todas las funciones
2. **Docstrings** en funciones publicas
3. **Pydantic** para validacion de entrada en API
4. **Nombres en espanol** para campos de negocio (proveedor, factura, etc.)
5. **Nombres en ingles** para codigo tecnico (buffer, elements, etc.)

---

## Manejo de Errores

```python
# En endpoints (api/main.py)
try:
    result = funcion_core(...)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.exception("Error interno")
    raise HTTPException(status_code=500, detail="Error interno")
```

---

## Archivos de Configuracion

### areas.csv
```csv
codigo;nombre
01;Area de Hacienda
02;Area de Recursos Humanos
...
```

### .env.example
```env
AREAS_CSV=areas.csv
TIMEZONE=Europe/Madrid
MAX_FILE_SIZE_MB=20
```

---

## Posibles Mejoras Futuras

1. **Caching** de PDFs generados (Redis)
2. **Validacion de firma** contra OCSP/CRL
3. **Soporte para adjuntos** en facturas (AttachedDocuments)
4. **Batch processing** para multiples facturas
5. **Webhook** para notificaciones de procesamiento
6. **Metricas** con Prometheus
7. **Tests de integracion** con archivos XSIG reales

---

## Archivos Clave para Modificaciones

| Tarea | Archivo |
|-------|---------|
| Nuevo endpoint | `api/main.py` |
| Cambiar formato PDF conformidad | `core/pdf.py` |
| Cambiar formato PDF factura XSIG | `core/xsig_pdf.py` |
| Agregar campo de XML | `core/xsig_pdf.py` -> `_extract_invoice_data_from_xml()` |
| Cambiar validaciones | `api/main.py` (modelos Pydantic) |
| Agregar dependencia | `requirements.txt` + `Dockerfile` |

---

## Contacto y Soporte

- **Organizacion:** Diputacion de Sevilla
- **Area:** Hacienda / Intervencion
- **Repositorio:** sical-ws

---

*Documento generado para facilitar el desarrollo asistido por IA.*
