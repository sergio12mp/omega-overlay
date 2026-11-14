; Instalador de Omega Overlay (Inno Setup 6). Lo llama build\build.ps1.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1D2B7A-4C3E-4E8B-9C21-0A7E5B3D9F10}
AppName=Omega Overlay
AppVersion={#AppVersion}
AppPublisher=Omega Overlay
AppComments=Overlay de OBS para Pokémon Rubí Omega / Zafiro Alfa en Azahar
DefaultDirName={autopf}\Omega Overlay
DefaultGroupName=Omega Overlay
DisableProgramGroupPage=yes
; Sin permisos de administrador: se instala para el usuario actual
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=OmegaOverlay-{#AppVersion}-instalador
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\OmegaOverlay.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\OmegaOverlay\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Omega Overlay"; Filename: "{app}\OmegaOverlay.exe"
Name: "{group}\Desinstalar Omega Overlay"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Omega Overlay"; Filename: "{app}\OmegaOverlay.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OmegaOverlay.exe"; Description: "{cm:LaunchProgram,Omega Overlay}"; Flags: nowait postinstall skipifsilent
