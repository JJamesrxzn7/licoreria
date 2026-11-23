<#
  Enciende en la LAPTOP todo lo que falte del clúster "La Cava":
    - 3 réplicas de la API (127.0.0.1:8001, 8002, 8003)
    - Balanceador round-robin (:8000)
    - Agentes 4, 5 y 6 (agentes_gye_cuenca.py)
  No toca lo que ya está corriendo. Los logs quedan en .\logs\

  Uso:
    .\iniciar_laptop.ps1            -> enciende lo que falte y termina
    .\iniciar_laptop.ps1 -Vigilar   -> además se queda vigilando cada 15 s y reenciende lo que se caiga
                                       (déjalo abierto durante la defensa; Ctrl+C para salir)

  Los agentes 1, 2 y 3 corren en la PC de Escritorio (agentes_quito.py): enciéndelos allá.
#>
param(
    [switch]$Vigilar,
    [int]$Intervalo = 15
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$api = Join-Path $root 'API'
$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Force $logs | Out-Null

# Elige el primer Python que tenga las librerías de la API (puede haber varias instalaciones)
$candidatos = @($env:LACAVA_PYTHON, "$env:LOCALAPPDATA\Python\bin\python3.14.exe") +
    @(Get-Command python, python3 -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
$py = $null
foreach ($c in $candidatos | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique) {
    & $c -c "import uvicorn, httpx, mysql.connector, psycopg, pymongo" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if (-not $py) { throw 'Ningún Python tiene las librerías de la API. Instálalas (pip install -r API\requirements.txt) o define $env:LACAVA_PYTHON.' }
Write-Host "Python: $py" -ForegroundColor DarkGray

function Test-Puerto([int]$Puerto) {
    [bool](Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue)
}

function Test-Proceso([string]$Patron) {
    [bool](Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
        Where-Object { $_.CommandLine -like "*$Patron*" })
}

function Stop-Zombi([string]$Patron) {
    # Proceso vivo cuyo puerto ya no escucha (p. ej. tras un WinError 64): se elimina antes de reencender
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
        Where-Object { $_.CommandLine -like "*$Patron*" } |
        ForEach-Object {
            Write-Host "         proceso colgado $($_.ProcessId) ($Patron) -> se cierra" -ForegroundColor DarkYellow
            try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
        }
}

function Start-Oculto([string]$Comando, [string]$Log) {
    # powershell oculto que ejecuta el comando y vuelca la salida al log
    $full = "$Comando *>> '$Log'"
    Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-Command', $full | Out-Null
}

function Get-ControlArquitecto {
    # Lo que el arquitecto de SI apagó a propósito desde la interfaz (pestaña 9) no se reenciende
    $archivo = Join-Path $logs 'control_arquitecto.json'
    if (Test-Path $archivo) {
        try { return Get-Content $archivo -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
    }
    return [pscustomobject]@{ replicasDesactivadas = @(); agentesPausados = $false }
}

function Invoke-Revision {
    $hora = Get-Date -Format 'HH:mm:ss'
    $control = Get-ControlArquitecto
    foreach ($i in 1..3) {
        $puerto = 8000 + $i
        if (Test-Puerto $puerto) { continue }
        if (@($control.replicasDesactivadas) -contains "api_lacava_$i") { continue }
        Write-Host "[$hora] Réplica api_lacava_$i (:$puerto) apagada -> encendiendo" -ForegroundColor Yellow
        Stop-Zombi "--port $puerto"
        Start-Oculto "`$env:API_REPLICA_ID='api_lacava_$i'; & '$py' -m uvicorn main:app --host 127.0.0.1 --port $puerto --app-dir '$api'" (Join-Path $logs "api_lacava_$i.log")
    }
    if (-not (Test-Puerto 8000)) {
        Write-Host "[$hora] Balanceador (:8000) apagado -> encendiendo" -ForegroundColor Yellow
        Stop-Zombi 'load_balancer_8080'
        # Se ejecuta el propio archivo: usa SelectorEventLoop, inmune al WinError 64 que tumbaba el accept
        Start-Oculto "Set-Location '$api'; & '$py' -u load_balancer_8080.py 8000" (Join-Path $logs 'balanceador.log')
    }
    if (-not $control.agentesPausados -and -not (Test-Proceso 'agentes_gye_cuenca.py')) {
        Write-Host "[$hora] Agentes 4-5-6 apagados -> encendiendo" -ForegroundColor Yellow
        Start-Oculto "Set-Location '$root'; & '$py' -u '$(Join-Path $root 'agentes_gye_cuenca.py')' --interval 60" (Join-Path $logs 'agentes_gye_cuenca.log')
    }
}

Invoke-Revision
Start-Sleep -Seconds 8

$estado = @(
    @{ n = 'Réplica 1 (:8001)'; ok = Test-Puerto 8001 },
    @{ n = 'Réplica 2 (:8002)'; ok = Test-Puerto 8002 },
    @{ n = 'Réplica 3 (:8003)'; ok = Test-Puerto 8003 },
    @{ n = 'Balanceador (:8000)'; ok = Test-Puerto 8000 },
    @{ n = 'Agentes 4-5-6'; ok = Test-Proceso 'agentes_gye_cuenca.py' }
)
foreach ($e in $estado) {
    $color = if ($e.ok) { 'Green' } else { 'Red' }
    $txt = if ($e.ok) { 'ENCENDIDO' } else { 'APAGADO (revisa logs\)' }
    Write-Host ("  {0,-22} {1}" -f $e.n, $txt) -ForegroundColor $color
}

if ($Vigilar) {
    Write-Host "`nVigilando cada $Intervalo s (Ctrl+C para salir)..." -ForegroundColor Cyan
    while ($true) {
        Start-Sleep -Seconds $Intervalo
        Invoke-Revision
    }
}
