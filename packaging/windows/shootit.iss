; Inno Setup script: per-user installer (no admin rights needed) -> Shootit-windows-x64-setup.exe
#ifndef Version
  #define Version "0.0.1"
#endif
#ifndef OutName
  #define OutName "Shootit-windows-x64-setup"
#endif

[Setup]
AppId={{B3F1A2C4-7D5E-4F6A-9B8C-1E2D3F4A5B6C}
AppName=Shootit
AppVersion={#Version}
AppPublisher=AWeebTaku
AppPublisherURL=https://github.com/AWeebTaku/Aim-Trainer
DefaultDirName={autopf}\Shootit
DefaultGroupName=Shootit
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..
OutputBaseFilename={#OutName}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\Shootit.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\Shootit\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Shootit"; Filename: "{app}\Shootit.exe"
Name: "{autodesktop}\Shootit"; Filename: "{app}\Shootit.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Shootit.exe"; Description: "Launch Shootit"; Flags: nowait postinstall skipifsilent
