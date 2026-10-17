#define AppVersion "0.1.0"
[Setup]
AppId={{083CA060-4E20-4B20-AD8D-F6DD8910DCC4}
AppName=Clipboard Sync
AppVersion={#AppVersion}
AppPublisher=Ding-Ding Projects
AppPublisherURL=https://github.com/Ding-Ding-Projects/clipboard-sync
DefaultDirName={localappdata}\Programs\ClipboardSync
DefaultGroupName=Clipboard Sync
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=ClipboardSync-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ClipboardSync.exe
[Files]
Source: "..\release\ClipboardSync.exe"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\Clipboard Sync"; Filename: "{app}\ClipboardSync.exe"
Name: "{autodesktop}\Clipboard Sync"; Filename: "{app}\ClipboardSync.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\ClipboardSync.exe"; Description: "Open Clipboard Sync"; Flags: nowait postinstall skipifsilent
