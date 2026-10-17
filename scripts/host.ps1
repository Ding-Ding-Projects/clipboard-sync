# Starts only this project's relay; never stops unrelated containers.
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ModeArgs)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
try {
    $detached = $ModeArgs -contains '--detached'
    $logs = $ModeArgs -contains '--logs'
    $pull = $ModeArgs -contains '--pull'
    foreach ($arg in $ModeArgs) { if ($arg -notin @('--detached','--logs','--pull')) { throw "Unknown option: $arg" } }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker Desktop is unavailable. Its Windows runtime requires system components and native consent, so this script cannot install it safely in user scope. Obtain Docker Desktop from https://www.docker.com/products/docker-desktop/ or use an existing Linux Docker host. No services were changed.'
    }
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is unavailable in the detected Docker installation.' }
    & docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is not ready. Start your existing Docker Desktop runtime and check its diagnostics.' }
    if (-not (Test-Path .env)) {
        $bytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $token = ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
        # Protect credentials before writing them; token values never go to output.
        $file = New-Item -Path .env -ItemType File
        $acl = New-Object Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true,$false)
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl.SetOwner($identity)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','Allow')))
        Set-Acl -Path $file.FullName -AclObject $acl
        [IO.File]::WriteAllText($file.FullName,"SERVER_TOKEN=$token`nSERVER_PORT=8787`n",(New-Object Text.UTF8Encoding($false)))
        $token = $null
        Write-Host 'Created protected local .env credentials. Share the token privately with your own computers.'
    }
    $port = '8787'
    foreach ($line in Get-Content .env) { if ($line -match '^SERVER_PORT=(\d+)$') { $port = $Matches[1] } }
    if ($env:SERVER_PORT) { $port = $env:SERVER_PORT }
    if ([int]$port -lt 1 -or [int]$port -gt 65535) { throw 'SERVER_PORT must be 1 through 65535.' }
    if (-not $detached -and -not $logs) {
        Write-Host '[D] Start detached  [L] Start with interactive logs  [Q] Cancel'
        do { $choice = [Console]::ReadKey($true).Key.ToString() } until ($choice -in @('D','L','Q'))
        if ($choice -eq 'Q') { exit 0 }
        $logs = $choice -eq 'L'
    }
    $compose = @('compose','--project-name','clipboard-sync-relay','--file','compose.yaml')
    if ($pull) {
        & docker @compose pull relay
        if ($LASTEXITCODE -ne 0) { throw 'Published image pull failed; no successful start is claimed.' }
        & docker @compose up --detach --no-build --pull never relay
    } else {
        & docker @compose up --detach --build relay
    }
    if ($LASTEXITCODE -ne 0) { throw 'Relay build/start failed. Review the Docker output above.' }
    $healthy = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try { $result = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2; if ($result.status -eq 'ok') { $healthy=$true; break } } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) { throw 'Relay did not become healthy within the startup deadline. Use docker compose --project-name clipboard-sync-relay logs relay.' }
    Write-Host "Healthy local server: http://127.0.0.1:$port/"
    $lanVerified = $false
    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.AddressState -eq 'Preferred' }
    foreach ($address in $addresses) {
        $url = "http://$($address.IPAddress):$port/"
        try { $check=Invoke-RestMethod ($url+'health') -TimeoutSec 2; if ($check.status -eq 'ok') { Write-Host "Verified host LAN endpoint: $url"; $lanVerified=$true } } catch {}
    }
    if (-not $lanVerified) { Write-Warning 'LAN health could not be verified. Check the selected network and existing firewall rules; external-computer reachability remains unverified.' }
    Write-Host 'Computer sync URL: ws://HOST-IP:'$port'/ws/home . Use the same private token and room on each computer.'
    if ($logs) {
        $follow = $true
        while ($true) {
            Clear-Host
            Write-Host 'Clipboard Sync Relay | selected service: relay'
            Write-Host '[F] Toggle live refresh  [R] Refresh now  [Q/Esc] Leave logs (server stays running)'
            & docker @compose ps relay
            & docker @compose logs --no-color --tail 20 relay
            if ($LASTEXITCODE -ne 0) { throw 'Could not read relay status/logs.' }
            $refreshAt = [DateTime]::UtcNow.AddSeconds(2)
            do {
                if ([Console]::KeyAvailable) {
                    $key = [Console]::ReadKey($true).Key.ToString()
                    if ($key -in @('Q','Escape')) { exit 0 }
                    if ($key -eq 'F') { $follow = -not $follow; break }
                    if ($key -eq 'R') { break }
                }
                Start-Sleep -Milliseconds 100
            } until ($follow -and [DateTime]::UtcNow -ge $refreshAt)
        }
    }
} catch { Write-Error $_; exit 1 }
