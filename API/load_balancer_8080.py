"""
Balanceador de Carga Round-Robin (`nginx_lb` equivalente en vivo) en el Puerto :8080 y :8000.
Reparte el tráfico HTTP en Round-Robin entre las 3 Réplicas Reales de `api_lacava`:
  - Réplica 1 (`api_lacava_1`) -> 127.0.0.1:8001
  - Réplica 2 (`api_lacava_2`) -> 127.0.0.1:8002
  - Réplica 3 (`api_lacava_3`) -> 127.0.0.1:8003
Y sirve también el Frontend compilado de "La Cava" (`frontend/dist`) en `http://<IP_TS_GUAYAQUIL>:8080/`.
Preserva el header obligatorio `X-Sede` (`QUITO`, `QUITO_NOSQL`, `QUITO_PARALELA`, `GUAYAQUIL`, `GUAYAQUIL_DWH`, `CUENCA`).
"""

import asyncio
import itertools
from pathlib import Path
import time
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

REPLICAS = [
    ("api_lacava_1", "http://127.0.0.1:8001"),
    ("api_lacava_2", "http://127.0.0.1:8002"),
    ("api_lacava_3", "http://127.0.0.1:8003"),
]
replica_cycle = itertools.cycle(REPLICAS)

lb_app = FastAPI(title="Nginx Load Balancer (:8080) - Round-Robin 3 Réplicas API La Cava")

lb_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Control del arquitecto de SI: se registra ANTES de la ruta general /api/{path} para que no se reenvíe a las réplicas
import control_arquitecto  # noqa: E402

lb_app.include_router(control_arquitecto.router)


def _cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    headers = {
        "Access-Control-Allow-Origin": origin or "*",
        "Access-Control-Allow-Private-Network": "true",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "*",
        "X-Load-Balancer": "nginx_lb_round_robin_8080",
    }
    if origin:
        headers["Vary"] = "Origin"
    return headers


@lb_app.get("/api/lb/estado")
async def load_balancer_status(request: Request):
    """Estado del balanceador: qué réplicas responden /healthz ahora mismo (lo usa la GUI para las alarmas)."""

    async def check(name: str, base: str) -> dict:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                r = await client.get(f"{base}/healthz")
            ok = r.status_code < 500
        except httpx.HTTPError:
            ok = False
        return {"replica": name, "url": base, "online": ok, "ms": round((time.perf_counter() - t0) * 1000, 1)}

    replicas = await asyncio.gather(*(check(n, b) for n, b in REPLICAS))
    online = sum(1 for r in replicas if r["online"])
    return JSONResponse(
        {"balanceador": "ONLINE", "replicasOnline": online, "replicasTotal": len(REPLICAS), "replicas": replicas},
        headers=_cors_headers(request),
    )


@lb_app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@lb_app.api_route("/healthz", methods=["GET"])
@lb_app.api_route("/readyz", methods=["GET"])
async def round_robin_proxy(request: Request, path: str = ""):
    target_path = request.url.path
    if request.url.query:
        target_path = f"{target_path}?{request.url.query}"

    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    # IP real del cliente para la auditoría (las réplicas solo ven al balanceador)
    if request.client and "x-forwarded-for" not in {k.lower() for k in headers}:
        headers["X-Forwarded-For"] = request.client.host

    # Round-robin con failover: si la réplica elegida no acepta la conexión, se prueba la siguiente.
    caidas: list[str] = []
    for _ in range(len(REPLICAS)):
        replica_name, base_url = next(replica_cycle)
        t_inicio = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request(
                    method=request.method,
                    url=f"{base_url}{target_path}",
                    content=body,
                    headers=headers,
                )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            caidas.append(replica_name)
            control_arquitecto.registrar_failover(replica_name)
            continue
        control_arquitecto.registrar_peticion(replica_name, resp.status_code, (time.perf_counter() - t_inicio) * 1000)

        out_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
        }
        out_headers.update(_cors_headers(request))
        out_headers["X-API-Replica"] = replica_name
        if caidas:
            out_headers["X-Replicas-Caidas"] = ",".join(caidas)
        return Response(content=resp.content, status_code=resp.status_code, headers=out_headers)

    return JSONResponse(
        status_code=503,
        content={
            "error": "API_SIN_REPLICAS",
            "detail": "El balanceador está activo pero las 3 réplicas de la API están apagadas. Ejecuta iniciar_laptop.ps1.",
            "replicasCaidas": caidas,
        },
        headers=_cors_headers(request),
    )


@lb_app.get("/licoreria/{full_path:path}", include_in_schema=False)
@lb_app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str = ""):
    clean_path = full_path.removeprefix("licoreria/").strip("/")
    if DIST_DIR.exists():
        candidate = DIST_DIR / clean_path
        if clean_path and candidate.is_file():
            return FileResponse(candidate)
        index_html = DIST_DIR / "index.html"
        if index_html.is_file():
            return FileResponse(index_html)
    return {
        "service": "nginx_lb_round_robin",
        "frontend_hosted_on": "GitHub Pages (https://jjamesrxzn7.github.io/licoreria)",
        "api_gateway": "http://100.123.81.4:8000/api",
        "replicas": [r[0] for r in REPLICAS],
        "status": "ONLINE",
    }


if __name__ == "__main__":
    # Arranque recomendado en Windows: `python load_balancer_8080.py [puerto]`.
    # El bucle Proactor (el que usa uvicorn por defecto en Windows) deja de aceptar conexiones para siempre
    # tras un WinError 64 (una conexión que se corta durante el accept): el proceso sigue vivo pero el puerto
    # queda cerrado. Con SelectorEventLoop ese error afecta solo a esa conexión.
    import sys

    import uvicorn

    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    servidor = uvicorn.Server(uvicorn.Config(lb_app, host="0.0.0.0", port=puerto, loop="none"))
    if sys.platform == "win32":
        asyncio.run(servidor.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(servidor.serve())
