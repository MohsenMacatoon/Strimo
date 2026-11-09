; Inno Setup script for Strimo  (build\make_installers.ps1 runs it twice: full and /DLITE)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Strimo"
#ifdef LITE
  #define Suffix "-Lite"
#else
  #define Suffix ""
#endif

[Setup]
AppId={{6C1F8E2A-3B9D-4F7A-9E51-2D8C4B7A1F30}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Strimo
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\output
OutputBaseFilename=Strimo-Setup-{#AppVersion}{#Suffix}
SetupIconFile=..\assets\strimo.ico
UninstallDisplayIcon={app}\Strimo.exe
UninstallDisplayName={#AppName}
Compression=lzma2/normal
SolidCompression=no
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "openwith"; Description: "Add Strimo to ""Open with"" for video and audio files"; GroupDescription: "Files:"

[Files]
Source: "..\dist\Strimo\*"; DestDir: "{app}"; Excludes: "tools\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\vendor\tools\yt-dlp.exe"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\vendor\tools\qjs.exe"; DestDir: "{app}\tools"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
#ifndef LITE
Source: "..\vendor\tools\ffmpeg.exe"; DestDir: "{app}\tools"; Flags: ignoreversion
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Strimo.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Strimo.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\Strimo.Media"; ValueType: string; ValueName: ""; ValueData: "Media file (Strimo)"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Strimo.Media\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Strimo.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Strimo.Media\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Strimo.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Strimo"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Strimo.exe"" ""%1"""; Tasks: openwith
; Windows only opens up to 15 selected files with Enter/"Open"; raise that limit for this user
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Explorer"; ValueType: dword; ValueName: "MultipleInvokePromptMinimum"; ValueData: "100000"; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Strimo.Media\shell\open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\shell\open"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Play"; ValueType: string; ValueName: ""; ValueData: "Play with Strimo"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Play"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Strimo.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Play"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Play\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Strimo.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Enqueue"; ValueType: string; ValueName: ""; ValueData: "Add to Strimo playlist"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Enqueue"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Strimo.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Enqueue"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\Strimo.Enqueue\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Strimo.exe"" --enqueue ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Play"; ValueType: string; ValueName: ""; ValueData: "Play with Strimo"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Play"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Strimo.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Play"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Play\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Strimo.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Enqueue"; ValueType: string; ValueName: ""; ValueData: "Add to Strimo playlist"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Enqueue"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Strimo.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Enqueue"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\Strimo.Enqueue\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Strimo.exe"" --enqueue ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Directory\shell\Strimo.PlayFolder"; ValueType: string; ValueName: ""; ValueData: "Play with Strimo"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Directory\shell\Strimo.PlayFolder"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Strimo.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Directory\shell\Strimo.PlayFolder\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Strimo.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".3g2"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".3gp"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".asf"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".avi"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".divx"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".f4v"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".flv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".m2ts"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".m4v"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mkv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mov"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mp4"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mpeg"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mpg"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mts"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mxf"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".ogv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".rm"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".rmvb"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".ts"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".vob"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".webm"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".wmv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".xvid"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".aac"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".ac3"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".aif"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".aiff"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".alac"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".amr"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".ape"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".dts"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".flac"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".m4a"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mka"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".mp3"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".oga"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".ogg"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".opus"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".wav"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".wma"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\Strimo.exe\SupportedTypes"; ValueType: string; ValueName: ".wv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.3g2\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.asf\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.divx\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.f4v\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.flv\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.m2ts\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mpeg\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mpg\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mts\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mxf\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ogv\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.rm\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.rmvb\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ts\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.vob\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wmv\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.xvid\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.aac\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ac3\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.aif\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.aiff\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.alac\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.amr\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ape\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.dts\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mka\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.oga\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.opus\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wma\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wv\OpenWithProgids"; ValueType: string; ValueName: "Strimo.Media"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
; Lets Strimo be chosen in Settings > Apps > Default apps (search "Strimo")
Root: HKA; Subkey: "Software\Strimo"; Flags: uninsdeletekeyifempty; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Strimo"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Ad-free video and music player"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\Strimo.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".3g2"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".3gp"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".asf"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".avi"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".divx"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".f4v"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flv"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m2ts"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4v"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mkv"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mov"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp4"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mpeg"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mpg"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mts"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mxf"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ogv"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".rm"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".rmvb"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ts"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".vob"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webm"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wmv"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".xvid"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aac"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ac3"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aif"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aiff"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".alac"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".amr"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ape"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".dts"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flac"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4a"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mka"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp3"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".oga"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ogg"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".opus"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wav"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wma"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\Strimo\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wv"; ValueData: "Strimo.Media"; Tasks: openwith
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Strimo"; ValueData: "Software\Strimo\Capabilities"; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\Strimo.exe"; Description: "Start Strimo now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\tools"
