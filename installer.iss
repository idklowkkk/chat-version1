; Cespo Installer Script for Inno Setup
; Build the exe first: pyinstaller --onefile --windowed --icon=icon.png --name=cespo main.py

[Setup]
AppName=Cespo
AppVersion=1.0.0
AppPublisher=Cespo
AppPublisherURL=https://github.com/cespo
DefaultDirName={autopf}\Cespo
DefaultGroupName=Cespo
OutputDir=installer_output
OutputBaseFilename=cespo-setup
SetupIconFile=icon.png
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\cespo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "guest-pfp.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Cespo"; Filename: "{app}\cespo.exe"; IconFilename: "{app}\icon.png"
Name: "{group}\Uninstall Cespo"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Cespo"; Filename: "{app}\cespo.exe"; IconFilename: "{app}\icon.png"; Tasks: desktopicon

[Run]
Filename: "{app}\cespo.exe"; Description: "{cm:LaunchProgram,Cespo}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
