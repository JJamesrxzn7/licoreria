"""
Balanceador de Carga Round-Robin (`nginx_lb` equivalente en vivo) en el Puerto :8080 y :8000.
Reparte el tráfico HTTP en Round-Robin entre las 3 Réplicas Reales de `api_lacava`:
  - Réplica 1 (`api_lacava_1`) -> 127.0.0.1:8001
  - Réplica 2 (`api_lacava_2`) -> 127.0.0.1:8002
  - Réplica 3 (`api_lacava_3`) -> 127.0.0.1:8003
Y sirve también el Frontend compilado de "La Cava" (`frontend/dist`) en `http://<IP_TS_GUAYAQUIL>:8080/`.
Preserva el header obligatorio `X-Sede` (`QUITO`, `QUITO_NOSQL`, `QUITO_PARALELA`, `GUAYAQUIL`, `GUAYAQUIL_DWH`, `CUENCA`).
"""

import itertools
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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


@lb_app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@lb_app.api_route("/healthz", methods=["GET"])
@lb_app.api_route("/readyz", methods=["GET"])
async def round_robin_proxy(request: Request, path: str = ""):
    replica_name, base_url = next(replica_cycle)
    target_path = request.url.path
    if request.url.query:
        target_path = f"{target_path}?{request.url.query}"
    url = f"{base_url}{target_path}"

    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers=headers,
        )

    out_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
    }
    origin = request.headers.get("origin")
    if origin:
        out_headers["Access-Control-Allow-Origin"] = origin
        out_headers["Vary"] = "Origin"
    else:
        out_headers["Access-Control-Allow-Origin"] = "*"
    out_headers["Access-Control-Allow-Private-Network"] = "true"
    out_headers["Access-Control-Allow-Headers"] = "*"
    out_headers["Access-Control-Allow-Methods"] = "*"
    out_headers["X-Load-Balancer"] = "nginx_lb_round_robin_8080"
    out_headers["X-API-Replica"] = replica_name
    return Response(content=resp.content, status_code=resp.status_code, headers=out_headers)


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
