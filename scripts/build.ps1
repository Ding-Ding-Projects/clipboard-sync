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
    $version = $env:PACKAGE_VERSION
    if (!$version) {
        $revision = if ($env:GITHUB_RUN_NUMBER) { $env:GITHUB_RUN_NUMBER } else { '0' }
        $version = "0.1.$revision"
    }
    if ($version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$' -or @($version.Split('.') | Where-Object { [long]$_ -gt 65535 }).Count -gt 0) {
        throw 'PACKAGE_VERSION must contain three numeric components, each between 0 and 65535.'
    }
    $versionParts = ($version.Split('.') + '0') -join ','
    $runtimeVersionFile = Join-Path $script:ToolRoot '_build_version.txt'
    $version | Set-Content -LiteralPath $runtimeVersionFile -Encoding UTF8
    $versionFile = Join-Path $script:ToolRoot 'receiver-version.txt'
    @"
VSVersionInfo(ffi=FixedFileInfo(filevers=($versionParts), prodvers=($versionParts), mask=0x3f, flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName', 'Ding-Ding Projects'), StringStruct('FileDescription', 'Clipboard Sync'), StringStruct('FileVersion', '$version'), StringStruct('ProductVersion', '$version'), StringStruct('ProductName', 'Clipboard Sync'), StringStruct('OriginalFilename', 'ClipboardSync.exe'), StringStruct('SquirrelAwareVersion', '1')])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"@ | Set-Content -LiteralPath $versionFile -Encoding UTF8
    $venvPython = Join-Path $script:ToolRoot 'venv\Scripts\python.exe'
    if (!(Test-Path $venvPython)) { Invoke-Checked $python @('-m','venv',(Join-Path $script:ToolRoot 'venv')) }
    Invoke-Checked $venvPython @('-m','pip','install','--disable-pip-version-check','-r','requirements.txt','pyinstaller==6.16.0')
    Invoke-Checked (Join-Path $nodeRoot 'npm.cmd') @('ci','--no-audit','--no-fund')
    Invoke-Checked (Join-Path $nodeRoot 'npm.cmd') @('run','build')
    Invoke-Checked $venvPython @('-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--name','ClipboardSync','--version-file',$versionFile,'--distpath','release','--workpath','build\pyinstaller','--specpath','build','--collect-submodules','receiver','--add-data',"$runtimeVersionFile;receiver",'--add-data',"$script:ProjectRoot\dist;dist",'--add-data',"$gitRoot;tools/git",'launcher.py')
    $exe = Join-Path $script:ProjectRoot 'release\ClipboardSync.exe'
    if (!(Test-Path $exe) -or (Get-Item $exe).Length -lt 1000000) { throw 'Executable output is missing or invalid.' }
    Write-Host "Portable Windows application: $exe"
    Get-FileHash $exe -Algorithm SHA256 | Format-List
    Invoke-Checked $venvPython @('-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--name','ClipboardSync-Guide','--distpath','release','--workpath','build\guide','--specpath','build','--add-data',"$script:ProjectRoot\docs;docs",'guide.py')
    if ($Installer) {
        $tools = Get-SquirrelTools
        $packageRoot = Join-Path $script:ProjectRoot 'build\packages'
        New-Item -ItemType Directory -Force $packageRoot | Out-Null
        $inputPackage = Join-Path $packageRoot "ClipboardSync.$version.nupkg"
        if (Test-Path $inputPackage) { Remove-Item -LiteralPath $inputPackage -Force }
        Invoke-Checked $tools.NuGet @('pack','scripts\ClipboardSync.nuspec','-Version',$version,'-BasePath',$script:ProjectRoot,'-OutputDirectory',$packageRoot,'-NoPackageAnalysis','-NonInteractive')
        if (!(Test-Path $inputPackage)) { throw "NuGet did not produce $inputPackage" }
        # A clean feed prevents a stale newer package from being embedded in this Setup.exe.
        # Delta packages require an explicitly supplied real previous feed; this build emits full packages.
        $feed = Join-Path $script:ProjectRoot 'build\squirrel-release'
        if (Test-Path $feed) { Remove-Item -LiteralPath $feed -Recurse -Force }
        New-Item -ItemType Directory -Force $feed | Out-Null
        Invoke-Checked $tools.Squirrel @('--releasify',$inputPackage,'--releaseDir',$feed,'--no-msi','--no-delta','--framework-version','net45')
        $setup = Join-Path $feed 'Setup.exe'
        $fullPackage = Join-Path $feed "ClipboardSync-$version-full.nupkg"
        $releases = Join-Path $feed 'RELEASES'
        if (!(Test-Path $setup) -or (Get-Item $setup).Length -lt 1000000 -or !(Test-Path $fullPackage) -or !(Test-Path $releases)) {
            throw 'Squirrel.Windows did not produce the complete Setup.exe, RELEASES and full .nupkg artifact set.'
        }
        # Validate the Squirrel feed against the actual full package, including its native SHA-1 record.
        $entry = (Get-Content -LiteralPath $releases -Raw).Trim() -split '\s+'
        if ($entry.Count -ne 3 -or $entry[1] -cne "ClipboardSync-$version-full.nupkg" -or
            $entry[0] -ine (Get-FileHash $fullPackage -Algorithm SHA1).Hash -or
            $entry[2] -ne [string](Get-Item $fullPackage).Length) {
            throw 'Squirrel RELEASES metadata does not match the emitted full package.'
        }
        Invoke-Checked $venvPython @('scripts\verify_squirrel.py',$feed,$version,$tools.Squirrel,$exe)
        # Only copy the feed generated in this invocation; obsolete feed files are not release assets.
        Get-ChildItem (Join-Path $script:ProjectRoot 'release') -File | Where-Object { $_.Name -eq 'RELEASES' -or $_.Extension -eq '.nupkg' -or $_.Name -in 'Setup.exe','ClipboardSync-Setup.exe' } | Remove-Item -Force
        Copy-Item -LiteralPath $setup,$releases,$fullPackage -Destination (Join-Path $script:ProjectRoot 'release') -Force
        Write-Host 'Squirrel.Windows artifacts are unsigned and may trigger unknown-publisher or SmartScreen warnings.'
        Write-Host 'Application data and local history are retained on uninstall. No delta was generated without a previous full package.'
    }
    $sourceCommit = & git rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot bind build artifacts to source commit.' }
    $artifactHashes = @{}
    Get-ChildItem (Join-Path $script:ProjectRoot 'release') -File | Where-Object { $_.Extension -in '.exe','.nupkg' -or $_.Name -eq 'RELEASES' } | ForEach-Object {
        $artifactHashes[$_.Name] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    @{ sourceCommit = $sourceCommit; version = $version; packaging = $(if ($Installer) { 'Squirrel.Windows 2.0.1; unsigned; full package only' } else { 'portable' }); builtAtUtc = [DateTime]::UtcNow.ToString('o'); artifacts = $artifactHashes; nativeWindowsAcceptance = 'not verified by build' } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $script:ProjectRoot 'release\build-receipt.json')
    if (!$silent) {
        $choice = Read-Host 'Build succeeded. Open Clipboard Sync now? [y/N]'
        if ($choice -match '^[yY]') { Start-Process -FilePath $exe }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.ToString())
    [Console]::Error.WriteLine($_.InvocationInfo.PositionMessage)
    [Console]::Error.WriteLine($_.ScriptStackTrace)
    exit 1
}
