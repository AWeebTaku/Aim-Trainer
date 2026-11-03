; Inno Setup script: per-user installer (no admin rights needed) -> Aim-Trainer-windows-x64-setup.exe
#ifndef Version
  #define Version "0.0.1"
#endif
#ifndef OutName
  #define OutName "Aim-Trainer-windows-x64-setup"
#endif

[Setup]
AppId={{B3F1A2C4-7D5E-4F6A-9B8C-1E2D3F4A5B6C}
AppName=Aim Trainer
AppVersion={#Version}
AppPublisher=AWeebTaku
AppPublisherURL=https://github.com/AWeebTaku/Aim-Trainer
DefaultDirName={autopf}\Aim Trainer
DefaultGroupName=Aim Trainer
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..
OutputBaseFilename={#OutName}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\Aim-Trainer.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\Aim-Trainer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Aim Trainer"; Filename: "{app}\Aim-Trainer.exe"
Name: "{autodesktop}\Aim Trainer"; Filename: "{app}\Aim-Trainer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Aim-Trainer.exe"; Description: "Launch Aim Trainer"; Flags: nowait postinstall skipifsilent
