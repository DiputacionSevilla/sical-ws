import os

# Carga .env (opcional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core.constants import (
    DEFAULT_ORACLE_CLIENT_DIR,
    DEFAULT_ORACLE_PORT,
    DEFAULT_ORACLE_HOST
)

cx_oracle_import_error = None
try:
    import oracledb as cx_Oracle
except Exception as e:
    cx_Oracle = None
    cx_oracle_import_error = e

_CLIENT_INITED = False

def get_cfg(key: str, default: str = "") -> str:
    return os.getenv(key, default)

def init_oracle_client_once():
    global _CLIENT_INITED
    if _CLIENT_INITED:
        return
    if cx_Oracle is None:
        raise RuntimeError(
            "No se pudo importar 'oracledb'. Instala con: pip install oracledb. "
            f"Detalle import: {cx_oracle_import_error}"
        )
    client_dir = get_cfg("ORACLE_CLIENT_DIR", DEFAULT_ORACLE_CLIENT_DIR)
    try:
        cx_Oracle.init_oracle_client(lib_dir=client_dir)
    except Exception as e:
        if "already initialized" not in str(e).lower():
            raise RuntimeError(f"No se pudo iniciar el cliente Oracle en '{client_dir}': {e}")
    _CLIENT_INITED = True

def get_connection():
    """
    Conecta a Oracle (modo THICK) usando SERVICE o SID.
    Variables esperadas: ORACLE_HOST, ORACLE_PORT, ORACLE_USER, ORACLE_PASSWORD, y ORACLE_SERVICE o ORACLE_SID
    """
    init_oracle_client_once()
    host = get_cfg("ORACLE_HOST", DEFAULT_ORACLE_HOST).strip()
    port = int(get_cfg("ORACLE_PORT", str(DEFAULT_ORACLE_PORT)).strip() or str(DEFAULT_ORACLE_PORT))
    user = get_cfg("ORACLE_USER", "").strip()
    pwd  = get_cfg("ORACLE_PASSWORD", "").strip()
    service = get_cfg("ORACLE_SERVICE", "").strip()
    sid     = get_cfg("ORACLE_SID", "").strip()

    faltan = [n for n, v in {
        "ORACLE_HOST": host, "ORACLE_PORT": port, "ORACLE_USER": user, "ORACLE_PASSWORD": pwd
    }.items() if not v]
    if not (service or sid):
        faltan.append("ORACLE_SERVICE/ORACLE_SID")
    if faltan:
        raise ValueError("Faltan variables de conexión: " + ", ".join(faltan))

    if service:
        dsn = cx_Oracle.makedsn(host, port, service_name=service)
    else:
        dsn = cx_Oracle.makedsn(host, port, sid=sid)

    try:
        conn = cx_Oracle.connect(user=user, password=pwd, dsn=dsn)
    except cx_Oracle.DatabaseError as e:
        raise ConnectionError(f"Fallo conectando a Oracle. DSN='{dsn}' Usuario='{user}'. Detalle: {e}")
    return conn
