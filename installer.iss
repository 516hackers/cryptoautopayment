; ============================================================
; Infinity Meta Hub — Windows Installer
; Built with Inno Setup 6
; Developed by Ayamil Coders
; ============================================================

#define AppName "Infinity Meta Hub"
#define AppVersion "4.0.0"
#define AppPublisher "Ayamil Coders"
#define AppExeName "InfinityMetaHub.exe"
#define AppURL "https://www.facebook.com/ayamilcoders"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

WizardImageFile=ayamil_banner.bmp
WizardImageStretch=yes
WizardSmallImageFile=ayamil_small.bmp
WizardStyle=modern

OutputDir=dist_installer
OutputBaseFilename=InfinityMetaHub_Setup_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes

UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
PrivilegesRequired=admin
ShowLanguageDialog=no

DisableWelcomePage=no
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartIfNeededByRun=yes
UninstallRestartComputer=no
DisableDirPage=no
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
  Description: "Create a &desktop shortcut"; \
  GroupDescription: "Shortcuts:"

[Files]
Source: "dist\InfinityMetaHub.exe"; DestDir: "{app}"; \
  Flags: ignoreversion; DestName: "{#AppExeName}"
Source: "ayamil.jpg"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
  Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; ============================================================
; Pascal Script
; ============================================================
[Code]
const
  NEW_VERSION = '4.0.0';

var
  PageAbout: TWizardPage;
  PageWallet: TWizardPage;
  LblAppTitle, LblDevBy, LblDesc, LblVersion: TLabel;
  LblSocialTitle, LblFacebook, LblInstagram: TLabel;
  LblWalletInfo, LblFromAddr, LblPKNote: TLabel;
  EdtFromAddr: TEdit;
  IsUpgradeMode: Boolean;

procedure OpenURL(const URL: string);
var
  ErrCode: Integer;
begin
  ShellExec('open', URL, '', '', SW_SHOWNORMAL, ewNoWait, ErrCode);
end;

procedure OnFacebookClick(Sender: TObject);
begin
  OpenURL('https://www.facebook.com/ayamilcoders');
end;

procedure OnInstagramClick(Sender: TObject);
begin
  OpenURL('https://www.instagram.com/ayamilcoders');
end;

function GetInstalledVersion: string;
var
  RegKey: string;
  InstalledVer: string;
begin
  RegKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' +
            '{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1';
  InstalledVer := '';
  if not RegQueryStringValue(HKLM64, RegKey, 'DisplayVersion', InstalledVer) then
    if not RegQueryStringValue(HKLM32, RegKey, 'DisplayVersion', InstalledVer) then
      RegQueryStringValue(HKCU, RegKey, 'DisplayVersion', InstalledVer);
  Result := InstalledVer;
end;

function InitializeSetup: Boolean;
var
  OldVer: string;
  Msg: string;
begin
  Result := True;
  OldVer := GetInstalledVersion;
  IsUpgradeMode := OldVer <> '';
  if IsUpgradeMode then
  begin
    Msg := '{#AppName} is already installed.' + #13#10 + #13#10 +
           'Installed version : ' + OldVer + #13#10 +
           'New version : ' + NEW_VERSION + #13#10 + #13#10 +
           'Click OK to upgrade, or Cancel to quit.';
    if MsgBox(Msg, mbConfirmation, MB_OKCANCEL) = IDCANCEL then
      Result := False;
  end;
end;

procedure InitializeWizard;
var
  AboutCaption, AboutSubCaption, DescText, OldVer: string;
begin
  OldVer := GetInstalledVersion;

  if IsUpgradeMode then
  begin
    AboutCaption := 'Upgrading {#AppName} to v' + NEW_VERSION;
    AboutSubCaption := 'Developed by {#AppPublisher} | Upgrade from v' + OldVer;
    DescText := 'You are upgrading from v' + OldVer + ' to v' + NEW_VERSION + '.' + #13#10 + #13#10 +
                'Settings and wallet config are preserved.';
  end
  else
  begin
    AboutCaption := 'Welcome to {#AppName}';
    AboutSubCaption := 'Developed by {#AppPublisher}';
    DescText := 'A professional admin tool for managing on-chain withdrawal requests.';
  end;

  PageAbout := CreateCustomPage(wpWelcome, AboutCaption, AboutSubCaption);

  // App Title
  LblAppTitle := TLabel.Create(PageAbout);
  with LblAppTitle do begin
    Parent := PageAbout.Surface;
    Caption := '{#AppName} v' + NEW_VERSION;
    Font.Size := 18;
    Font.Style := [fsBold];
    Font.Color := clLime;
    Left := 0;
    Top := 0;
    AutoSize := True;
  end;

  // Developer
  LblDevBy := TLabel.Create(PageAbout);
  with LblDevBy do begin
    Parent := PageAbout.Surface;
    Caption := 'Developed by {#AppPublisher}';
    Font.Size := 10;
    Font.Color := clGray;
    Left := 0;
    Top := 34;
    AutoSize := True;
  end;

  // Version Badge
  LblVersion := TLabel.Create(PageAbout);
  with LblVersion do begin
    Parent := PageAbout.Surface;
    if IsUpgradeMode then
      Caption := ' UPGRADE: v' + OldVer + ' → v' + NEW_VERSION + ' '
    else
      Caption := ' NEW INSTALL v' + NEW_VERSION + ' ';
    Font.Size := 9;
    Font.Style := [fsBold];
    if IsUpgradeMode then Font.Color := clBlue else Font.Color := clLime;
    Left := 0;
    Top := 56;
    AutoSize := True;
  end;

  // Description
  LblDesc := TLabel.Create(PageAbout);
  with LblDesc do begin
    Parent := PageAbout.Surface;
    Caption := DescText;
    Font.Size := 9;
    Left := 0;
    Top := 82;
    Width := 440;
    Height := 170;
    AutoSize := False;
    WordWrap := True;
  end;

  // Social Links
  LblSocialTitle := TLabel.Create(PageAbout);
  with LblSocialTitle do begin
    Parent := PageAbout.Surface;
    Caption := 'Follow Ayamil Coders:';
    Font.Size := 9;
    Font.Style := [fsBold];
    Left := 0;
    Top := 262;
    AutoSize := True;
  end;

  LblFacebook := TLabel.Create(PageAbout);
  with LblFacebook do begin
    Parent := PageAbout.Surface;
    Caption := ' Facebook: facebook.com/ayamilcoders';
    Font.Color := clBlue;
    Font.Style := [fsUnderline];
    Cursor := crHand;
    Left := 0; Top := 284;
    AutoSize := True;
    OnClick := @OnFacebookClick;
  end;

  LblInstagram := TLabel.Create(PageAbout);
  with LblInstagram do begin
    Parent := PageAbout.Surface;
    Caption := ' Instagram: instagram.com/ayamilcoders';
    Font.Color := clPurple;
    Font.Style := [fsUnderline];
    Cursor := crHand;
    Left := 0; Top := 308;
    AutoSize := True;
    OnClick := @OnInstagramClick;
  end;

  // Wallet Setup Page
  PageWallet := CreateCustomPage(PageAbout.ID, 'Wallet Setup',
    'Pre-configure your sending wallet (you can change later)');

  LblWalletInfo := TLabel.Create(PageWallet);
  with LblWalletInfo do begin
    Parent := PageWallet.Surface;
    if IsUpgradeMode then
      Caption := 'You are upgrading an existing installation.' + #13#10#13#10 +
                 'Your wallet settings are already saved.' + #13#10#13#10 +
                 'Click Next to continue.'
    else
      Caption := 'Enter the wallet address that will send USDT / BH tokens.' + #13#10 +
                 'This wallet must hold gas + sufficient tokens.';
    Font.Size := 9;
    Left := 0; Top := 0;
    Width := 460; Height := 100;
    AutoSize := False; WordWrap := True;
  end;

  LblFromAddr := TLabel.Create(PageWallet);
  with LblFromAddr do begin
    Parent := PageWallet.Surface;
    Caption := 'From Wallet Address:';
    Font.Size := 9;
    Font.Style := [fsBold];
    Left := 0;
    Top := 110;
    AutoSize := True;
    Visible := not IsUpgradeMode;
  end;

  EdtFromAddr := TEdit.Create(PageWallet);
  with EdtFromAddr do begin
    Parent := PageWallet.Surface;
    Text := '';
    Left := 0;
    Top := 132;
    Width := 460;
    Font.Name := 'Consolas';
    Font.Size := 9;
    Visible := not IsUpgradeMode;
    Enabled := not IsUpgradeMode;
  end;

  LblPKNote := TLabel.Create(PageWallet);
  with LblPKNote do begin
    Parent := PageWallet.Surface;
    if IsUpgradeMode then
      Caption := '✔ Upgrade preserves your encrypted private key.'
    else
      Caption := '⚠ PRIVATE KEY is NOT entered here. You will set it inside the app.';
    Font.Size := 9;
    Font.Color := clLime;
    Left := 0;
    Top := 172;
    Width := 460;
    Height := 140;
    AutoSize := False;
    WordWrap := True;
  end;
end;

procedure WriteInitialConfig(const FromAddress: string);
var
  ConfigDir, ConfigPath, ConfigJson: string;
begin
  ConfigDir := ExpandConstant('{userappdata}') + '\.withdrawal_admin';
  ConfigPath := ConfigDir + '\config.json';
  if FileExists(ConfigPath) then Exit;
  if not DirExists(ConfigDir) then CreateDir(ConfigDir);

  ConfigJson :=
    '{' + #13#10 +
    ' "api_base_url": "https://yourdomain.com/api/v1/admin/withdrawals",' + #13#10 +
    ' "auth_header": "",' + #13#10 +
    ' "network": "polygon_bh",' + #13#10 +
    ' "rpc_url": "https://polygon-rpc.com",' + #13#10 +
    ' "token_contract": "0x68a6EA8e9aB0824251061DD122aDA8493e62409d",' + #13#10 +
    ' "decimals": 18,' + #13#10 +
    ' "amount_source": "bh",' + #13#10 +
    ' "from_address": "' + FromAddress + '",' + #13#10 +
    ' "simulate_only": true,' + #13#10 +
    ' "pk_set": false,' + #13#10 +
    ' "pk_salt": "",' + #13#10 +
    ' "pk_token": "",' + #13#10 +
    ' "extra_tokens": [],' + #13#10 +
    ' "app_version": "' + NEW_VERSION + '"' + #13#10 +
    '}';
  SaveStringToFile(ConfigPath, ConfigJson, False);
end;

procedure UpdateConfigVersion;
var
  ConfigPath, OldContent, NewContent, VerLine: string;
begin
  ConfigPath := ExpandConstant('{userappdata}') + '\.withdrawal_admin\config.json';
  if not FileExists(ConfigPath) then Exit;
  if not LoadStringFromFile(ConfigPath, OldContent) then Exit;

  VerLine := '"app_version": "' + NEW_VERSION + '"';
  if Pos('"app_version"', OldContent) = 0 then
  begin
    NewContent := Copy(OldContent, 1, Length(OldContent) - 1);
    while (Length(NewContent) > 0) and 
          ((NewContent[Length(NewContent)] = ' ') or 
           (NewContent[Length(NewContent)] = #13) or 
           (NewContent[Length(NewContent)] = #10)) do
      Delete(NewContent, Length(NewContent), 1);
    NewContent := NewContent + ',' + #13#10 + ' ' + VerLine + #13#10 + '}';
    SaveStringToFile(ConfigPath, NewContent, False);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsUpgradeMode then
      UpdateConfigVersion
    else
      WriteInitialConfig(EdtFromAddr.Text);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PageWallet.ID) and (not IsUpgradeMode) then
  begin
    if (Length(EdtFromAddr.Text) > 0) and (Length(EdtFromAddr.Text) < 42) then
    begin
      MsgBox('Wallet address looks too short.' + #13#10 +
             'A valid address starts with "0x" and is 42 characters long.' + #13#10#13#10 +
             'You can leave it blank.', mbInformation, MB_OK);
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if IsUpgradeMode and (CurPageID = wpReady) then
    WizardForm.NextButton.Caption := '&Update';
end;
