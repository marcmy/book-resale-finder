#ifndef MyAppVersion
  #define MyAppVersion "0.2.1"
#endif
#ifndef RepoRoot
  #define RepoRoot "..\\.."
#endif

[Setup]
AppId={{7F9336DE-808D-4C26-B91F-71B77E6AD86A}
AppName=Sourcing Cockpit
AppVersion={#MyAppVersion}
AppPublisher=marcmy
DefaultDirName={localappdata}\Programs\SourcingCockpit
DefaultGroupName=Sourcing Cockpit
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#RepoRoot}\sourcing_cockpit\dist\installer
OutputBaseFilename=SourcingCockpit-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SourcingCockpitHelper.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start Sourcing Cockpit automatically when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
Source: "{#RepoRoot}\sourcing_cockpit\dist\SourcingCockpitHelper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\sourcing_cockpit\build\firefox\SourcingCockpit.xpi"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\Sourcing Cockpit"; Filename: "{app}\SourcingCockpitHelper.exe"; Parameters: "--configure"
Name: "{userstartup}\Sourcing Cockpit"; Filename: "{app}\SourcingCockpitHelper.exe"; Parameters: "--background"; Tasks: startup

[Run]
Filename: "{app}\SourcingCockpitHelper.exe"; Parameters: "--configure"; Description: "Configure Sourcing Cockpit"; Flags: nowait postinstall skipifsilent
Filename: "{app}\SourcingCockpit.xpi"; Description: "Install the Firefox extension"; Flags: shellexec postinstall skipifsilent; Check: SignedXpiPresent

[Code]
function SignedXpiPresent(): Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\SourcingCockpit.xpi'));
end;
