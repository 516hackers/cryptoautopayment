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
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\InfinityMetaHub.exe"; DestDir: "{app}"; Flags: ignoreversion; DestName: "{#AppExeName}"
Source: "ayamil.jpg"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

; ============================================================
; Pascal Script - CLEAN VERSION (No problematic 'with' blocks)
; ============================================================
[Code]
const
  NEW_VERSION = '4.0.0';

var
  PageAbout: TWizardPage;
  PageWallet: TWizardPage;
  IsUpgradeMode: Boolean;

  LblAppTitle, LblDevBy, LblDesc, LblVersion: TLabel;
  LblSocialTitle, LblFacebook, LblInstagram: TLabel;
  LblWalletInfo, LblFromAddr, LblPKNote: TLabel;
  EdtFromAddr: TEdit;

procedure OpenURL(const URL: string);
var ErrCode: Integer;
begin
  ShellExec('open', URL, '', '', SW_SHOWNORMAL, ewNoWait, ErrCode);
end;

procedure OnFacebookClick(Sender: TObject); begin OpenURL('https://www.facebook.com/ayamilcoders'); end;
procedure OnInstagramClick(Sender: TObject); begin OpenURL('https://www.instagram.com/ayamilcoders'); end;

function GetInstalledVersion: string;
var RegKey, InstalledVer: string;
begin
  RegKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1';
  InstalledVer := '';
  if not RegQueryStringValue(HKLM64, RegKey, 'DisplayVersion', InstalledVer) then
    if not RegQueryStringValue(HKLM32, RegKey, 'DisplayVersion', InstalledVer) then
      RegQueryStringValue(HKCU, RegKey, 'DisplayVersion', InstalledVer);
  Result := InstalledVer;
end;

function InitializeSetup: Boolean;
var OldVer, Msg: string;
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
var AboutCaption, AboutSubCaption, DescText, OldVer: string;
begin
  OldVer := GetInstalledVersion;

  if IsUpgradeMode then
  begin
    AboutCaption := 'Upgrading {#AppName} to v' + NEW_VERSION;
    AboutSubCaption := 'Upgrade from v' + OldVer;
    DescText := 'Settings and wallet are preserved.';
  end
  else
  begin
    AboutCaption := 'Welcome to {#AppName}';
    AboutSubCaption := 'Developed by {#AppPublisher}';
    DescText := 'Professional admin tool for on-chain withdrawals.';
  end;

  PageAbout := CreateCustomPage(wpWelcome, AboutCaption, AboutSubCaption);

  // === About Page Controls ===
  LblAppTitle := TLabel.Create(PageAbout);
  LblAppTitle.Parent := PageAbout.Surface;
  LblAppTitle.Caption := '{#AppName} v' + NEW_VERSION;
  LblAppTitle.Font.Size := 18;
  LblAppTitle.Font.Style := [fsBold];
  LblAppTitle.Font.Color := clLime;
  LblAppTitle.Left := 0;
  LblAppTitle.Top := 0;
  LblAppTitle.AutoSize := True;

  LblDevBy := TLabel.Create(PageAbout);
  LblDevBy.Parent := PageAbout.Surface;
  LblDevBy.Caption := 'Developed by {#AppPublisher}';
  LblDevBy.Font.Size := 10;
  LblDevBy.Font.Color := clGray;
  LblDevBy.Left := 0;
  LblDevBy.Top := 34;
  LblDevBy.AutoSize := True;

  LblVersion := TLabel.Create(PageAbout);
  LblVersion.Parent := PageAbout.Surface;
  if IsUpgradeMode then
    LblVersion.Caption := ' UPGRADE: v' + OldVer + ' → v' + NEW_VERSION + ' '
  else
    LblVersion.Caption := ' NEW INSTALL v' + NEW_VERSION + ' ';
  LblVersion.Font.Size := 9;
  LblVersion.Font.Style := [fsBold];
  if IsUpgradeMode then LblVersion.Font.Color := clBlue else LblVersion.Font.Color := clLime;
  LblVersion.Left := 0;
  LblVersion.Top := 56;
  LblVersion.AutoSize := True;

  LblDesc := TLabel.Create(PageAbout);
  LblDesc.Parent := PageAbout.Surface;
  LblDesc.Caption := DescText;
  LblDesc.Font.Size := 9;
  LblDesc.Left := 0;
  LblDesc.Top := 82;
  LblDesc.Width := 440;
  LblDesc.Height := 170;
  LblDesc.AutoSize := False;
  LblDesc.WordWrap := True;

  LblSocialTitle := TLabel.Create(PageAbout);
  LblSocialTitle.Parent := PageAbout.Surface;
  LblSocialTitle.Caption := 'Follow Ayamil Coders:';
  LblSocialTitle.Font.Size := 9;
  LblSocialTitle.Font.Style := [fsBold];
  LblSocialTitle.Left := 0;
  LblSocialTitle.Top := 262;
  LblSocialTitle.AutoSize := True;

  LblFacebook := TLabel.Create(PageAbout);
  LblFacebook.Parent := PageAbout.Surface;
  LblFacebook.Caption := ' Facebook: facebook.com/ayamilcoders';
  LblFacebook.Font.Color := clBlue;
  LblFacebook.Font.Style := [fsUnderline];
  LblFacebook.Cursor := crHand;
  LblFacebook.Left := 0;
  LblFacebook.Top := 284;
  LblFacebook.AutoSize := True;
  LblFacebook.OnClick := @OnFacebookClick;

  LblInstagram := TLabel.Create(PageAbout);
  LblInstagram.Parent := PageAbout.Surface;
  LblInstagram.Caption := ' Instagram: instagram.com/ayamilcoders';
  LblInstagram.Font.Color := clPurple;
  LblInstagram.Font.Style := [fsUnderline];
  LblInstagram.Cursor := crHand;
  LblInstagram.Left := 0;
  LblInstagram.Top := 308;
  LblInstagram.AutoSize := True;
  LblInstagram.OnClick := @OnInstagramClick;

  // === Wallet Page ===
  PageWallet := CreateCustomPage(PageAbout.ID, 'Wallet Setup', 'Pre-configure your sending wallet');

  LblWalletInfo := TLabel.Create(PageWallet);
  LblWalletInfo.Parent := PageWallet.Surface;
  if IsUpgradeMode then
    LblWalletInfo.Caption := 'You are upgrading.' + #13#10#13#10 + 'Your wallet settings are preserved.' + #13#10#13#10 + 'Click Next.'
  else
    LblWalletInfo.Caption := 'Enter the wallet address that will send tokens.' + #13#10 + 'Must have gas + sufficient balance.';
  LblWalletInfo.Font.Size := 9;
  LblWalletInfo.Left := 0;
  LblWalletInfo.Top := 0;
  LblWalletInfo.Width := 460;
  LblWalletInfo.Height := 100;
  LblWalletInfo.AutoSize := False;
  LblWalletInfo.WordWrap := True;

  LblFromAddr := TLabel.Create(PageWallet);
  LblFromAddr.Parent := PageWallet.Surface;
  LblFromAddr.Caption := 'From Wallet Address:';
  LblFromAddr.Font.Size := 9;
  LblFromAddr.Font.Style := [fsBold];
  LblFromAddr.Left := 0;
  LblFromAddr.Top := 110;
  LblFromAddr.AutoSize := True;
  LblFromAddr.Visible := not IsUpgradeMode;

  EdtFromAddr := TEdit.Create(PageWallet);
  EdtFromAddr.Parent := PageWallet.Surface;
  EdtFromAddr.Text := '';
  EdtFromAddr.Left := 0;
  EdtFromAddr.Top := 132;
  EdtFromAddr.Width := 460;
  EdtFromAddr.Font.Name := 'Consolas';
  EdtFromAddr.Font.Size := 9;
  EdtFromAddr.Visible := not IsUpgradeMode;
  EdtFromAddr.Enabled := not IsUpgradeMode;

  LblPKNote := TLabel.Create(PageWallet);
  LblPKNote.Parent := PageWallet.Surface;
  if IsUpgradeMode then
    LblPKNote.Caption := '✔ Your encrypted private key is preserved.'
  else
    LblPKNote.Caption := '⚠ PRIVATE KEY will be set securely inside the app.';
  LblPKNote.Font.Size := 9;
  LblPKNote.Font.Color := clLime;
  LblPKNote.Left := 0;
  LblPKNote.Top := 172;
  LblPKNote.Width := 460;
  LblPKNote.Height := 140;
  LblPKNote.AutoSize := False;
  LblPKNote.WordWrap := True;
end;

procedure WriteInitialConfig(const FromAddress: string);
var ConfigDir, ConfigPath, ConfigJson: string;
begin
  ConfigDir := ExpandConstant('{userappdata}\.withdrawal_admin');
  ConfigPath := ConfigDir + '\config.json';
  if FileExists(ConfigPath) then Exit;
  if not DirExists(ConfigDir) then CreateDir(ConfigDir);

  ConfigJson := '{' + #13#10 +
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
    ' "app_version": "' + NEW_VERSION + '"' + #13#10 + '}';
  SaveStringToFile(ConfigPath, ConfigJson, False);
end;

procedure UpdateConfigVersion;
var ConfigPath, OldContent, NewContent, VerLine: string;
begin
  ConfigPath := ExpandConstant('{userappdata}\.withdrawal_admin\config.json');
  if not FileExists(ConfigPath) then Exit;
  if not LoadStringFromFile(ConfigPath, OldContent) then Exit;

  VerLine := '"app_version": "' + NEW_VERSION + '"';
  if Pos('"app_version"', OldContent) = 0 then
  begin
    NewContent := Copy(OldContent, 1, Length(OldContent)-1);
    while (Length(NewContent) > 0) and ((NewContent[Length(NewContent)] = ' ') or (NewContent[Length(NewContent)] = #13) or (NewContent[Length(NewContent)] = #10)) do
      Delete(NewContent, Length(NewContent), 1);
    NewContent := NewContent + ',' + #13#10 + ' ' + VerLine + #13#10 + '}';
    SaveStringToFile(ConfigPath, NewContent, False);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    if IsUpgradeMode then UpdateConfigVersion
    else WriteInitialConfig(EdtFromAddr.Text);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PageWallet.ID) and (not IsUpgradeMode) then
    if (Length(EdtFromAddr.Text) > 0) and (Length(EdtFromAddr.Text) < 42) then
      MsgBox('Wallet address too short. Valid address is 42 chars starting with 0x.' + #13#10#13#10 + 'You can leave it blank.', mbInformation, MB_OK);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if IsUpgradeMode and (CurPageID = wpReady) then
    WizardForm.NextButton.Caption := '&Update';
end;
