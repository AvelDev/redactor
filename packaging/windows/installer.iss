; Inno Setup script. Build:  iscc /DAppVersion=0.1.0 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6C2B7C1E-3A57-4C5B-9C2E-7E7B5D2F8A11}
AppName=Redactor
AppVersion={#AppVersion}
AppPublisher=Redactor
DefaultDirName={autopf}\Redactor
DefaultGroupName=Redactor
OutputDir=..\..\dist
OutputBaseFilename=Redactor-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\build\icon.ico
UninstallDisplayIcon={app}\Redactor.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\Redactor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Redactor"; Filename: "{app}\Redactor.exe"
Name: "{autodesktop}\Redactor"; Filename: "{app}\Redactor.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\Applications\Redactor.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey

[Run]
Filename: "{app}\Redactor.exe"; Description: "{cm:LaunchProgram,Redactor}"; Flags: nowait postinstall skipifsilent
