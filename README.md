# Informe de Conformidad - API REST

API REST para la generacion de informes de conformidad de facturas y procesamiento de facturas electronicas XSIG/XML.

## Descripcion

Servicio web desarrollado con FastAPI que permite:

- **Generacion de informes PDF** de conformidad/no conformidad
- **Procesamiento de facturas electronicas** (XSIG/XML de FACe)
- **Generacion de resumenes de factura** desde datos JSON
- **Extraccion de datos de factura** con soporte para multiples tipos de IVA

## Caracteristicas

- API REST pura (sin interfaz web)
- Sin dependencias de base de datos externa
- Soporte para firma electronica XAdES
- Desglose de impuestos multiples (IVA, IRPF, Recargo de Equivalencia)
- Detalles de pago (IBAN, fecha vencimiento, forma de pago)
- Despliegue con Docker

## Requisitos

- Python 3.12 o superior
- Docker (opcional, para despliegue en contenedor)

## Instalacion

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd acta-conformidad
```

### 2. Crear entorno virtual

```bash
python -m venv venv
venv\Scripts\activate  # En Windows
# source venv/bin/activate  # En Linux/Mac
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar areas

Edita el archivo `areas.csv` segun tu configuracion:

```csv
codigo;nombre
1200;Area de Hacienda
1300;Area de Recursos Humanos
```

## Uso

### Iniciar el servidor

```bash
# Opcion 1: Directamente con uvicorn
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Opcion 2: Ejecutando el modulo
python -m api.main
```

La API estara disponible en: http://localhost:8000

Documentacion interactiva (Swagger): http://localhost:8000/docs

## Despliegue con Docker

### Construir la imagen

```bash
docker build -t face-pdf-api .
```

### Ejecutar el contenedor

```bash
docker run -d -p 8000:8000 --name face-pdf-api face-pdf-api
```

### Despliegue en Render

El proyecto incluye `render.yaml` para despliegue automatico en Render.com:

```yaml
services:
  - type: web
    name: face-pdf-api
    runtime: docker
    plan: free
    healthCheckPath: /health
```

## Endpoints de la API

### GET /health

Comprobacion de estado del servicio.

```bash
curl http://localhost:8000/health
```

Respuesta:
```json
{"status": "ok"}
```

### POST /api/informe

Genera un PDF de informe de conformidad o no conformidad.

**Content-Type:** `application/json`

**Parametros:**

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| `num_rcf` | string | Si | Numero RCF |
| `punto_entrada` | string | No | Punto de entrada (ej. "FACe") |
| `id_punto_entrada` | string | No | ID del punto de entrada |
| `fecha_hora_entrada` | string | No | Fecha/hora de entrada |
| `proveedor` | string | No | Nombre del proveedor |
| `nif_proveedor` | string | No | NIF del proveedor |
| `fecha_expedicion` | string | No | Fecha de expedicion |
| `vfacnum` | string | No | Numero de factura |
| `importe_total` | string | No | Importe total |
| `concepto` | string | No | Concepto de la factura |
| `area_code` | string | No | Codigo de area |
| `area_name` | string | No | Nombre del area |
| `resultado_conformidad` | string | No | "conforme" o "no_conforme" |
| `motivo_no_conformidad` | string | Condicional | Requerido si no_conforme |
| `aplicaciones` | array | No | Lista de aplicaciones presupuestarias |
| `observaciones` | string | No | Texto libre de observaciones |

**Ejemplo:**

```bash
curl -X POST http://localhost:8000/api/informe \
  -H "Content-Type: application/json" \
  -d '{
    "num_rcf": "2025-0001",
    "proveedor": "Proveedor Ejemplo S.A.",
    "nif_proveedor": "A12345678",
    "importe_total": "1.234,56",
    "resultado_conformidad": "conforme"
  }' \
  --output informe.pdf
```

### POST /api/xml2pdf

Convierte una factura electronica XSIG/XML a PDF representativo.

**Content-Type:** `multipart/form-data`

**Parametros:**

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| `file` | file | Si | Archivo XSIG o XML |
| `num_registro` | string | Si | Numero de registro |
| `tipo_registro` | string | Si | Tipo de registro |
| `num_rcf` | string | Si | Numero RCF |
| `fecha_registro` | string | No | Fecha ISO 8601 |

**Ejemplo:**

```bash
curl -X POST http://localhost:8000/api/xml2pdf \
  -F "file=@factura.xsig" \
  -F "num_registro=12345" \
  -F "tipo_registro=FACe" \
  -F "num_rcf=2025-0001" \
  --output factura.pdf
```

**Campos soportados en XSIG/XML:**

- Datos de emisor y receptor (nombre, NIF, direccion)
- Centros administrativos (OfiCont, OrgGest, UndTram)
- Lineas de factura con descripcion, cantidad, precio e importe
- Periodo de facturacion por linea
- **Desglose de impuestos (TaxesOutputs)**: Soporte para multiples tipos de IVA
- **Recargo de equivalencia (EquivalenceSurcharge)**
- **Detalles de pago (PaymentDetails)**: IBAN, fecha vencimiento, forma de pago
- Retenciones (IRPF, etc.)
- Firma electronica XAdES con validacion de certificado

### POST /api/factura

Genera un PDF de resumen de factura desde datos JSON.

**Content-Type:** `application/json`

**Ejemplo:**

```bash
curl -X POST http://localhost:8000/api/factura \
  -H "Content-Type: application/json" \
  -d '{
    "factura": {
      "numero": "F-2025-001",
      "fecha": "15/01/2025",
      "moneda": "EUR"
    },
    "emisor": {
      "Nombre": "Proveedor S.L.",
      "NIF": "B12345678"
    }
  }' \
  --output resumen.pdf
```

### POST /api/datosfactura

Genera un PDF con datos detallados de factura desde JSON.

**Content-Type:** `application/json`

**Ejemplo:**

```bash
curl -X POST http://localhost:8000/api/datosfactura \
  -H "Content-Type: application/json" \
  -d '{
    "generales": {
      "nfacreg": "2025-0001",
      "proveedor": "Proveedor S.L.",
      "vfacnum": "F-001",
      "nbasimp": 1000.00,
      "nfaciva": 210.00,
      "nfacimp": 1210.00
    },
    "aplicaciones": [
      {
        "organica": "1200",
        "funcional": "1510",
        "economica": "226.06",
        "importe": 1210.00
      }
    ]
  }' \
  --output datos_factura.pdf
```

## Estructura del Proyecto

```
acta-conformidad/
├── api/
│   └── main.py            # API FastAPI con todos los endpoints
├── core/
│   ├── config.py          # Configuracion de la aplicacion
│   ├── constants.py       # Constantes
│   ├── pdf.py             # Generacion de PDFs (informes)
│   ├── xsig_pdf.py        # Procesamiento de facturas XSIG/XML
│   ├── service.py         # Servicios de generacion de PDF
│   ├── factura_pdf.py     # PDF de resumen de factura
│   ├── datosfactura_pdf.py # PDF de datos de factura
│   ├── areas.py           # Gestion de areas
│   └── utils.py           # Utilidades generales
├── images/                # Recursos graficos (logos)
├── areas.csv              # Configuracion de areas
├── requirements.txt       # Dependencias Python
├── Dockerfile             # Imagen Docker
├── .dockerignore          # Exclusiones para Docker
└── render.yaml            # Configuracion de Render.com
```

## Dependencias

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.9
pydantic>=2.0.0
reportlab==4.2.0
cryptography==43.0.0
python-dateutil==2.9.0
pytz==2024.1
python-dotenv==1.0.0
```

## Seguridad

- Validacion de entrada en todos los campos con Pydantic
- Sanitizacion de nombres de archivo
- CORS configurable (restringir en produccion)
- Usuario no-root en contenedor Docker

## Desarrollo

### Ejecutar tests

```bash
pytest tests/
```

### Linting

```bash
flake8 core/ api/
```

## Variables de Entorno

| Variable | Descripcion | Default |
|----------|-------------|---------|
| `AREAS_CSV` | Archivo CSV de areas | areas.csv |
| `TIMEZONE` | Zona horaria | Europe/Madrid |
| `MAX_FILE_SIZE_MB` | Tamano maximo de archivo | 20 |
| `PYTHONUNBUFFERED` | Salida sin buffer (Docker) | 1 |
| `TZ` | Zona horaria del sistema | Europe/Madrid |

## Solucion de Problemas

### Error: "Archivo vacio o ilegible"
- Verifica que el archivo XSIG/XML no este corrupto
- Comprueba que el archivo tenga contenido

### Error: "El archivo no parece un XSIG/XML valido"
- Verifica que el formato sea Facturae v3.2 o compatible
- Comprueba que el XML este bien formado

### Error 500 en endpoints
- Revisa los logs del servidor para mas detalles
- Verifica que todas las dependencias esten instaladas

## Licencia

[Especificar licencia]

## Autores

Diputacion de Sevilla - Area de Hacienda

## Soporte

Para soporte tecnico, contactar a: [email de soporte]
