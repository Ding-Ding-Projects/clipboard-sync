param([switch]$Installer, [Parameter(ValueFromRemainingArguments=$true)][string[]]$Remaining)
$ErrorActionPreference = 'Stop'
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Native packaging requires Windows 10/11 x64.' }
    $silent = $env:SILENT -eq '1' -or @($Remaining | Where-Object { $_ -in '/s','--silent' }).Count -gt 0
    . "$PSScriptRoot\toolchain.ps1"
    Set-Location $script:ProjectRoot
    Write-Host 'Build uses project-local tools and needs no administrator rights.'
    $python = Get-Python
    $nodeRoot = Get-Node
    $gitRoot = Get-PortableGit
    $env:PATH = "$nodeRoot;$gitRoot\cmd;" + $env:PATH
    $venvPython = Join-Path $script:ToolRoot 'venv\Scripts\python.exe'
    if (!(Test-Path $venvPython)) { Invoke-Checked $python @('-m','venv',(Join-Path $script:ToolRoot 'venv')) }
    Invoke-Checked $venvPython @('-m','pip','install','--disable-pip-version-check','-r','requirements.txt','pyinstaller==6.16.0')
    Invoke-Checked (Join-Path $nodeRoot 'npm.cmd') @('ci','--no-audit','--no-fund')
    Invoke-Checked (Join-Path $nodeRoot 'npm.cmd') @('run','build')
    Invoke-Checked $venvPython @('-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--name','ClipboardSync','--distpath','release','--workpath','build\pyinstaller','--specpath','build','--collect-submodules','receiver','--add-data',"$script:ProjectRoot\dist;dist",'--add-data',"$gitRoot;tools/git",'launcher.py')
    $exe = Join-Path $script:ProjectRoot 'release\ClipboardSync.exe'
    if (!(Test-Path $exe) -or (Get-Item $exe).Length -lt 1000000) { throw 'Executable output is missing or invalid.' }
    Write-Host "Portable Windows application: $exe"
    Get-FileHash $exe -Algorithm SHA256 | Format-List
    Invoke-Checked $venvPython @('-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--name','ClipboardSync-Guide','--distpath','release','--workpath','build\guide','--specpath','build','--add-data',"$script:ProjectRoot\docs;docs",'guide.py')
    if ($Installer) {
        $innoRoot = Join-Path $script:ToolRoot 'inno'
        $compiler = Join-Path $innoRoot 'ISCC.exe'
        if (!(Test-Path $compiler)) {
            $innoInstaller = Get-VerifiedFile 'https://github.com/jrsoftware/issrc/releases/download/is-6_4_3/innosetup-6.4.3.exe' 'innosetup-6.4.3.exe' 'f3c42116542c4cc57263c5ba6c4feabfc49fe771f2f98a79d2f7628b8762723b'
            $result = Start-Process -FilePath $innoInstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',('/DIR="'+$innoRoot+'"')) -Wait -PassThru
            if ($result.ExitCode -ne 0) { throw "Inno Setup user-scoped install failed: $($result.ExitCode)" }
        }
        Invoke-Checked $compiler @('scripts\installer.iss')
        $setup = Join-Path $script:ProjectRoot 'release\ClipboardSync-Setup.exe'
        if (!(Test-Path $setup) -or (Get-Item $setup).Length -lt 1000000) { throw 'Installer output is missing or invalid.' }
        Write-Host 'Installer is unsigned. Application data and local history are retained on uninstall.'
        Get-FileHash $setup -Algorithm SHA256 | Format-List
    }
    $sourceCommit = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot bind build artifacts to source commit.' }
    $artifactHashes = @{}
    Get-ChildItem (Join-Path $script:ProjectRoot 'release\*.exe') | ForEach-Object {
        $artifactHashes[$_.Name] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    @{ sourceCommit = $sourceCommit; version = '0.1.0'; builtAtUtc = [DateTime]::UtcNow.ToString('o'); artifacts = $artifactHashes; nativeWindowsAcceptance = 'not verified by build' } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $script:ProjectRoot 'release\build-receipt.json')
    if (!$silent) {
        $choice = Read-Host 'Build succeeded. Open Clipboard Sync now? [y/N]'
        if ($choice -match '^[yY]') { Start-Process -FilePath $exe }
    }
    exit 0
} catch {
    Write-Error $_
    exit 1
}
