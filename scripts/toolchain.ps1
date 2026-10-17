$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path $PSScriptRoot -Parent
$script:ToolRoot = Join-Path $script:ProjectRoot '.toolchain'
New-Item -ItemType Directory -Force $script:ToolRoot | Out-Null

function Get-VerifiedFile([string]$Url, [string]$Name, [string]$Sha256) {
    $destination = Join-Path $script:ToolRoot $Name
    if (Test-Path $destination) {
        if ((Get-FileHash $destination -Algorithm SHA256).Hash -eq $Sha256) { return $destination }
        Remove-Item -LiteralPath $destination -Force
    }
    Write-Host "Downloading pinned dependency: $Name"
    $partial = "$destination.partial"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing
    if ((Get-FileHash $partial -Algorithm SHA256).Hash -ne $Sha256) {
        Remove-Item -LiteralPath $partial -Force
        throw "SHA-256 verification failed for $Name from $Url"
    }
    Move-Item -LiteralPath $partial -Destination $destination -Force
    return $destination
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}

function Get-Python {
    $existing = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($existing -and $existing.Source -notmatch 'WindowsApps') {
        & $existing.Source -c 'import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] < (3,14) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $existing.Source }
    }
    $python = Join-Path $script:ToolRoot 'python\python.exe'
    if (!(Test-Path $python)) {
        $installer = Get-VerifiedFile 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' 'python-3.12.10-amd64.exe' '67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb'
        $target = Join-Path $script:ToolRoot 'python'
        $result = Start-Process -FilePath $installer -ArgumentList @('/quiet','InstallAllUsers=0','Include_launcher=0','Include_test=0','PrependPath=0',('TargetDir="' + $target + '"')) -Wait -PassThru
        if ($result.ExitCode -ne 0) { throw "Python per-user install failed: exit $($result.ExitCode). No restart was initiated." }
    }
    Invoke-Checked $python @('-c','import sys; print(sys.version)')
    return $python
}

function Get-Node {
    $existing = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($existing) {
        & $existing.Source -e 'process.exit(Number(process.versions.node.split(".")[0])>=22?0:1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return Split-Path $existing.Source -Parent }
    }
    $nodeRoot = Join-Path $script:ToolRoot 'node-v22.14.0-win-x64'
    if (!(Test-Path (Join-Path $nodeRoot 'node.exe'))) {
        $archive = Get-VerifiedFile 'https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip' 'node-v22.14.0-win-x64.zip' '55b639295920b219bb2acbcfa00f90393a2789095b7323f79475c9f34795f217'
        Expand-Archive -LiteralPath $archive -DestinationPath $script:ToolRoot -Force
    }
    return $nodeRoot
}

function Get-PortableGit {
    $gitRoot = Join-Path $script:ToolRoot 'git'
    if (!(Test-Path (Join-Path $gitRoot 'cmd\git.exe'))) {
        $archive = Get-VerifiedFile 'https://github.com/git-for-windows/git/releases/download/v2.49.0.windows.1/MinGit-2.49.0-64-bit.zip' 'MinGit-2.49.0-64-bit.zip' '971cdee7c0feaa1e41369c46da88d1000a24e79a6f50191c820100338fb7eca5'
        Expand-Archive -LiteralPath $archive -DestinationPath $gitRoot -Force
    }
    return $gitRoot
}

function Get-SquirrelTools {
    # Both downloads use canonical publishers and fixed SHA-256 values. No signer is invoked.
    $nuget = Get-VerifiedFile 'https://dist.nuget.org/win-x86-commandline/v6.14.0/nuget.exe' 'nuget-6.14.0.exe' '92dbed160ddee0f64b901e907439e021211b428e57c089ecc12fc38dcc4bd9a5'
    $package = Get-VerifiedFile 'https://api.nuget.org/v3-flatcontainer/squirrel.windows/2.0.1/squirrel.windows.2.0.1.nupkg' 'squirrel.windows.2.0.1.nupkg' '923e18abb4fd50b5a4878a39dbcd042ed3f7eb68fc0f82c0955cd5380c921ac7'
    $squirrelRoot = Join-Path $script:ToolRoot 'squirrel.windows.2.0.1'
    # Re-extract from the verified archive rather than trusting an old executable cache.
    $zip = Join-Path $script:ToolRoot 'squirrel.windows.2.0.1.zip'
    Copy-Item -LiteralPath $package -Destination $zip -Force
    Expand-Archive -LiteralPath $zip -DestinationPath $squirrelRoot -Force
    Remove-Item -LiteralPath $zip -Force
    $squirrel = Join-Path $squirrelRoot 'tools\Squirrel.exe'
    if (!(Test-Path $squirrel)) { throw 'Verified Squirrel.Windows 2.0.1 package lacks tools\Squirrel.exe.' }
    # Supported Windows 10/11 include .NET Framework 4.7.2 or newer; NuGet requires it.
    $framework = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full' -ErrorAction SilentlyContinue
    if (!$framework -or $framework.Release -lt 461808) {
        throw 'NuGet 6.14.0 requires .NET Framework 4.7.2 or newer, included with supported Windows 10/11. Repair the Windows .NET Framework installation.'
    }
    return @{ NuGet = $nuget; Squirrel = $squirrel }
}
