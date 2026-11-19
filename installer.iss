; PDF Analyst - установщик для Windows 10/11 (x64)
; Требуется Inno Setup 6.x
; Перед компиляцией: build_desktop.bat (собирает dist\PDF Analyst\)
; Результат: ОДИН файл dist\installer\PDF-Analyst-Setup.exe
;
; Установщик проверяет недостающие компоненты и предлагает их установить:
;   - Microsoft Edge WebView2 Runtime (окно приложения без браузера)
;   - Visual C++ Redistributable 2015-2022 x64 (библиотеки Python-зависимостей)
;   - Tesseract OCR (только для распознавания сканов; требуется ручная установка с rus/eng)

#define MyAppName "PDF Analyst"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "PDF Analyst"
#define MyAppExeName "PDF Analyst.exe"

[Setup]
AppId={{D7A6D9B1-3F44-4E8A-9D8E-8A2A7C4C1B10}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\installer
OutputBaseFilename=PDF-Analyst-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
; Если компонент уже скачан/build-машиной, можно включить Next в пустом виде

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\PDF Analyst\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Пользовательские данные (%LOCALAPPDATA%\PDF Analyst\data) НЕ удаляются


[Code]
{ ---------- Загрузка файлов через WinAPI urlmon.dll ---------- }
function URLDownloadToFileA(pCaller: LongWord; szUrl: AnsiString;
  szFileName: AnsiString; dwReserved: LongWord; lpfnCB: LongWord): LongWord;
  external 'URLDownloadToFileA@urlmon.dll stdcall';

function DownloadFile(const Url, DestFile: String): Boolean;
begin
  Result := False;
  try
    Result := (URLDownloadToFileA(0, Url, DestFile, 0, 0) = 0) and FileExists(DestFile);
  except
    Result := False;
  end;
end;

{ ---------- Проверки компонентов ---------- }
function IsWebView2Installed(): Boolean;
begin
  Result :=
    RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKEY_CURRENT_USER, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}');
end;

function IsVCRedistInstalled(): Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}vcruntime140.dll')) and
            FileExists(ExpandConstant('{sys}vcruntime140_1.dll'));
end;

function IsTesseractInstalled(): Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{localappdata}\Programs\Tesseract-OCR\tesseract.exe')) or
    FileExists('C:\Program Files\Tesseract-OCR\tesseract.exe') or
    FileExists('C:\Program Files (x86)\Tesseract-OCR\tesseract.exe');
end;

function IsWindows10OrLater(): Boolean;
var
  WinVersion: TWindowsVersion;
begin
  GetWindowsVersionEx(WinVersion);
  Result := WinVersion.Major >= 10;
end;

{ ---------- Тихая установка скачанного компонента ---------- }
function InstallDownloaded(const Url, FileName, Params: String; var Msg: String): Boolean;
var
  Tmp: String;
  Code: Integer;
begin
  Result := False;
  Msg := '';
  Tmp := AddBackslash(GetTempDir()) + FileName;
  if FileExists(Tmp) then
    DeleteFile(Tmp);
  if not DownloadFile(Url, Tmp) then
  begin
    Msg := 'не удалось скачать ' + FileName;
    Exit;
  end;
  if not Exec(Tmp, Params, '', SW_HIDE, ewWaitUntilTerminated, Code) then
  begin
    Msg := 'не удалось запустить ' + FileName;
    Exit;
  end;
  { 0 = успех, 3010 = успех, требуется перезагрузка }
  Result := (Code = 0) or (Code = 3010);
  if not Result then
    Msg := FileName + ' завершился с кодом ' + IntToStr(Code);
end;

{ ---------- Главная проверка (перед началом копирования файлов) ---------- }
function PrepareInstall(): Boolean;
var
  NeedWeb, NeedVC, NeedTess: Boolean;
  Answer, Ans, Code: Integer;
  Msg, Errors: String;
  Ok: Boolean;
begin
  Result := True;

  NeedWeb  := not IsWebView2Installed();
  NeedVC   := not IsVCRedistInstalled();
  NeedTess := not IsTesseractInstalled();

  if (not NeedWeb) and (not NeedVC) and (not NeedTess) then
    Exit;

  Msg := 'Для корректной работы приложения не найдены компоненты:' + #13#10 + #13#10;
  if NeedWeb  then Msg := Msg + '  • Microsoft Edge WebView2 Runtime — отдельное окно приложения' + #13#10;
  if NeedVC   then Msg := Msg + '  • Visual C++ Redistributable 2015-2022 x64 — библиотеки зависимостей' + #13#10;
  if NeedTess then Msg := Msg + '  • Tesseract OCR — распознавание сканов (необязательно)' + #13#10;
  Msg := Msg + #13#10 +
    'WebView2 и VC++ можно установить автоматически (требуется интернет).' + #13#10 +
    'Tesseract нужно установить вручную с языками rus и eng.' + #13#10 + #13#10 +
    'Установить недостающие компоненты сейчас?';

  Answer := MsgBox(Msg, mbConfirmation, MB_YESNO);
  if Answer <> IDYES then
    Exit;

  Errors := '';

  if NeedVC then
  begin
    Ok := InstallDownloaded(
      'https://aka.ms/vs/17/release/vc_redist.x64.exe',
      'vc_redist.x64.exe', '/install /quiet /norestart', Msg);
    if not Ok then Errors := Errors + '  • VC++: ' + Msg + #13#10;
  end;

  if NeedWeb then
  begin
    Ok := InstallDownloaded(
      'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
      'WebView2RuntimeInstallerX64.exe', '/silent /install', Msg);
    if not Ok then Errors := Errors + '  • WebView2: ' + Msg + #13#10;
  end;

  if NeedTess then
  begin
    ShellExec('open', 'https://github.com/UB-Mannheim/tesseract/wiki',
      '', '', SW_SHOWNORMAL, ewNoWait, Code);
    Errors := Errors + '  • Tesseract: открыта страница загрузки (установите с rus+eng)' + #13#10;
  end;

  if Errors <> '' then
    MsgBox('Некоторые компоненты установить не удалось:' + #13#10 + #13#10 + Errors + #13#10 +
      'Приложение будет установлено. Повторите установку компонентов вручную при необходимости.',
      mbError, MB_OK);
end;

function InitializeSetup(): Boolean;
var
  Ans: Integer;
begin
  Result := True;
  if not UsingWinNT then
  begin
    MsgBox('Требуется Windows NT.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  if not IsWindows10OrLater() then
  begin
    Ans := MsgBox('Эта сборка предназначена для Windows 10/11 x64. ' +
      'На вашей версии Windows working не гарантирована. Продолжить?',
      mbConfirmation, MB_YESNO);
    if Ans <> IDYES then
      Result := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
    PrepareInstall();
end;
