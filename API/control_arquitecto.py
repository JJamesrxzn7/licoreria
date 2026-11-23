"""
Control del ARQUITECTO DE SI (lo atiende el propio balanceador, no las réplicas):
  - Encender / apagar cada réplica de la API (scale-out y failover con un clic).
  - Pausar / reanudar los agentes de la Laptop (agentes_gye_cuenca.py).
  - Métricas del SERVICIO medidas en el balanceador: peticiones/min, p50/p95 de tiempo de respuesta,
    errores 5xx y failovers por réplica (las métricas del DBA son las del motor; estas son las de la capa de aplicación).
  - Estado de la red Tailscale (cada par: conexión directa o por relay).

Lo apagado a propósito queda en logs/control_arquitecto.json: el vigilante (iniciar_laptop.ps1 -Vigilar) lo lee
y NO lo reenciende hasta que el arquitecto lo vuelva a encender.

Seguridad: cada acción exige el token de un administrador, que se valida en una réplica viva
(GET /api/arquitecto/autorizar). Si no queda ninguna réplica viva, solo se aceptan peticiones desde la propia Laptop.
"""

import asyncio
import json
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "API"
LOGS = ROOT / "logs"
CONTROL_FILE = LOGS / "control_arquitecto.json"
PYTHON = sys.executable

REPLICAS_CTRL = {1: ("api_lacava_1", 8001), 2: ("api_lacava_2", 8002), 3: ("api_lacava_3", 8003)}

router = APIRouter(tags=["Control del arquitecto de SI (balanceador)"])

# ------------------------------------------------------------------------------------------------
# Métricas del servicio (las registra el balanceador en cada petición que reparte)
# ------------------------------------------------------------------------------------------------
_METRICAS: deque = deque(maxlen=50000)  # (timestamp, replica, status, ms)
_FAILOVERS: deque = deque(maxlen=5000)  # (timestamp, replica_caida)
INICIO = time.time()


def registrar_peticion(replica: str, status: int, ms: float) -> None:
    _METRICAS.append((time.time(), replica, status, ms))


def registrar_failover(replica_caida: str) -> None:
    _FAILOVERS.append((time.time(), replica_caida))


def _percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    v = sorted(valores)
    k = max(0, min(len(v) - 1, int(round(p / 100 * (len(v) - 1)))))
    return round(v[k], 1)


def resumen_metricas() -> dict[str, Any]:
    ahora = time.time()
    ultimo_min = [m for m in _METRICAS if ahora - m[0] <= 60]
    ultimos_5 = [m for m in _METRICAS if ahora - m[0] <= 300]
    por_replica = {}
    for nombre, _p in REPLICAS_CTRL.values():
        r1 = [m for m in ultimo_min if m[1] == nombre]
        r5 = [m for m in ultimos_5 if m[1] == nombre]
        tiempos = [m[3] for m in r5]
        por_replica[nombre] = {
            "peticionesUltimoMinuto": len(r1),
            "peticiones5min": len(r5),
            "p50ms": _percentil(tiempos, 50),
            "p95ms": _percentil(tiempos, 95),
            "errores5xx5min": sum(1 for m in r5 if m[2] >= 500),
        }
    tiempos = [m[3] for m in ultimos_5]
    return {
        "ventanaSegundos": 300,
        "desdeHace": int(ahora - INICIO),
        "totalUltimoMinuto": len(ultimo_min),
        "total5min": len(ultimos_5),
        "p50ms": _percentil(tiempos, 50),
        "p95ms": _percentil(tiempos, 95),
        "errores5xx5min": sum(1 for m in ultimos_5 if m[2] >= 500),
        "failovers5min": sum(1 for f in _FAILOVERS if ahora - f[0] <= 300),
        "porReplica": por_replica,
    }


# ------------------------------------------------------------------------------------------------
# Estado y archivo de control
# ------------------------------------------------------------------------------------------------

def _leer_control() -> dict[str, Any]:
    try:
        return json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"replicasDesactivadas": [], "agentesPausados": False, "historial": []}


def _guardar_control(ctrl: dict[str, Any]) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    CONTROL_FILE.write_text(json.dumps(ctrl, ensure_ascii=False, indent=2), encoding="utf-8")


def _anotar(ctrl: dict[str, Any], usuario: str, accion: str) -> None:
    ctrl.setdefault("historial", []).insert(0, {"fecha": datetime.now().isoformat(timespec="seconds"), "usuario": usuario, "accion": accion})
    ctrl["historial"] = ctrl["historial"][:30]


def _ps(comando: str, timeout: int = 20) -> str:
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", comando], capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "").strip()


def _procesos_python(patron: str) -> list[int]:
    salida = _ps(
        "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{patron}*' }} | ForEach-Object {{ $_.ProcessId }}"
    )
    return [int(x) for x in salida.split() if x.strip().isdigit()]


def _puerto_escucha(puerto: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _iniciar_oculto(comando: str, log: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", f"{comando} *>> '{LOGS / log}'"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
        close_fds=True,
    )


_TS_CACHE: dict[str, Any] = {"t": 0, "data": None}


def _estado_tailscale() -> dict[str, Any]:
    if time.time() - _TS_CACHE["t"] < 10 and _TS_CACHE["data"]:
        return _TS_CACHE["data"]
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=8)
        data = json.loads(r.stdout or "{}")
        pares = []
        for p in (data.get("Peer") or {}).values():
            ip = (p.get("TailscaleIPs") or [""])[0]
            directa = bool(p.get("CurAddr"))
            pares.append({
                "host": p.get("HostName"), "ip": ip, "online": bool(p.get("Online")),
                "conexion": "directa" if directa else (f"relay ({p.get('Relay')})" if p.get("Relay") else "sin tráfico reciente"),
                "direccion": p.get("CurAddr") or None,
            })
        yo = data.get("Self") or {}
        res = {"ok": True, "estadoBackend": data.get("BackendState"), "yo": {"host": yo.get("HostName"), "ip": (yo.get("TailscaleIPs") or [""])[0]},
               "pares": pares, "topologia": "malla (WireGuard punto a punto; relay DERP como respaldo)"}
    except Exception as exc:
        res = {"ok": False, "error": str(exc)[:200], "pares": []}
    _TS_CACHE.update(t=time.time(), data=res)
    return res


def _estado_actual() -> dict[str, Any]:
    ctrl = _leer_control()
    replicas = []
    for n, (nombre, puerto) in REPLICAS_CTRL.items():
        replicas.append({"numero": n, "replica": nombre, "puerto": puerto, "online": _puerto_escucha(puerto),
                         "apagadaPorArquitecto": nombre in ctrl.get("replicasDesactivadas", [])})
    return {
        "timestamp": datetime.now().isoformat(),
        "balanceador": {"puerto": 8000, "algoritmo": "round-robin con failover", "online": True},
        "replicas": replicas,
        "agentesLaptop": {"script": "agentes_gye_cuenca.py", "corriendo": bool(_procesos_python("agentes_gye_cuenca.py")),
                          "pausadosPorArquitecto": bool(ctrl.get("agentesPausados"))},
        "vigilante": {"corriendo": "iniciar_laptop.ps1" in _ps(
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*iniciar_laptop.ps1*-Vigilar*' } | "
            "ForEach-Object { 'iniciar_laptop.ps1' } | Select-Object -First 1")},
        "metricas": resumen_metricas(),
        "tailscale": _estado_tailscale(),
        "historial": ctrl.get("historial", [])[:15],
    }


# ------------------------------------------------------------------------------------------------
# Autorización
# ------------------------------------------------------------------------------------------------

async def _autorizar(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    for nombre, puerto in REPLICAS_CTRL.values():
        if not _puerto_escucha(puerto):
            continue
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.get(f"http://127.0.0.1:{puerto}/api/arquitecto/autorizar", headers={"Authorization": auth})
        except httpx.HTTPError:
            continue
        if r.status_code == 200:
            return r.json().get("usuario", "admin")
        detalle = (r.json() or {}).get("detail") if r.headers.get("content-type", "").startswith("application/json") else None
        raise HTTPException(status_code=r.status_code, detail=detalle or "No autorizado.")
    # Ninguna réplica viva para validar: solo desde la propia Laptop
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost"):
        return "admin (local, sin réplicas)"
    raise HTTPException(status_code=503, detail="No hay réplicas para validar la sesión; opera desde la propia Laptop.")


# ------------------------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------------------------

@router.get("/api/lb/arquitecto/estado")
async def arquitecto_estado():
    return await asyncio.to_thread(_estado_actual)


@router.post("/api/lb/arquitecto/replica/{numero}/{accion}")
async def arquitecto_replica(numero: int, accion: str, request: Request):
    if numero not in REPLICAS_CTRL or accion not in ("apagar", "encender"):
        raise HTTPException(status_code=404, detail="Use /replica/1..3/apagar|encender")
    usuario = await _autorizar(request)
    nombre, puerto = REPLICAS_CTRL[numero]
    ctrl = _leer_control()
    desactivadas = set(ctrl.get("replicasDesactivadas", []))

    if accion == "apagar":
        vivas = [p for n, (_, p) in REPLICAS_CTRL.items() if n != numero and _puerto_escucha(p)]
        if not vivas:
            raise HTTPException(status_code=409, detail="Es la última réplica encendida: apagarla dejaría la API sin servicio.")
        desactivadas.add(nombre)
        ctrl["replicasDesactivadas"] = sorted(desactivadas)
        _anotar(ctrl, usuario, f"Apagó {nombre} (:{puerto})")
        _guardar_control(ctrl)  # primero el archivo, para que el vigilante no la reencienda
        pids = await asyncio.to_thread(_procesos_python, f"--port {puerto}")
        await asyncio.to_thread(_ps, " ; ".join(f"Stop-Process -Id {p} -Force -ErrorAction SilentlyContinue" for p in pids) or "$null")
    else:
        desactivadas.discard(nombre)
        ctrl["replicasDesactivadas"] = sorted(desactivadas)
        _anotar(ctrl, usuario, f"Encendió {nombre} (:{puerto})")
        _guardar_control(ctrl)
        if not _puerto_escucha(puerto):
            _iniciar_oculto(
                f"$env:API_REPLICA_ID='{nombre}'; & '{PYTHON}' -m uvicorn main:app --host 127.0.0.1 --port {puerto} --app-dir '{API_DIR}'",
                f"{nombre}.log",
            )
        for _ in range(40):  # hasta ~20 s a que arranque
            if _puerto_escucha(puerto):
                break
            await asyncio.sleep(0.5)
    return {"ok": True, "accion": accion, "replica": nombre, "usuario": usuario, "estado": await asyncio.to_thread(_estado_actual)}


@router.post("/api/lb/arquitecto/agentes/{accion}")
async def arquitecto_agentes(accion: str, request: Request):
    if accion not in ("pausar", "reanudar"):
        raise HTTPException(status_code=404, detail="Use /agentes/pausar|reanudar")
    usuario = await _autorizar(request)
    ctrl = _leer_control()
    if accion == "pausar":
        ctrl["agentesPausados"] = True
        _anotar(ctrl, usuario, "Pausó los agentes 4-5-6 (y la replicación automática)")
        _guardar_control(ctrl)
        pids = await asyncio.to_thread(_procesos_python, "agentes_gye_cuenca.py")
        await asyncio.to_thread(_ps, " ; ".join(f"Stop-Process -Id {p} -Force -ErrorAction SilentlyContinue" for p in pids) or "$null")
    else:
        ctrl["agentesPausados"] = False
        _anotar(ctrl, usuario, "Reanudó los agentes 4-5-6")
        _guardar_control(ctrl)
        if not await asyncio.to_thread(_procesos_python, "agentes_gye_cuenca.py"):
            _iniciar_oculto(f"Set-Location '{ROOT}'; & '{PYTHON}' -u '{ROOT / 'agentes_gye_cuenca.py'}' --interval 60", "agentes_gye_cuenca.log")
            await asyncio.sleep(2)
    return {"ok": True, "accion": accion, "usuario": usuario, "estado": await asyncio.to_thread(_estado_actual)}
