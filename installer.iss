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

; Wizard banner BMP (164x314) and small BMP (55x58) are generated
; from ayamil.jpg by the build pipeline (see build.yml).
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

; ── Upgrade / reinstall behaviour ────────────────────────────────────
; When the same AppId is already installed Inno Setup enters "upgrade"
; mode automatically.  The flags below control that flow:
;   • DisableWelcomePage=no   — still show our custom About page
;   • CloseApplications=yes   — ask user to close the running app
;   • RestartIfNeededByRun=yes— offer restart if files were locked
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
; Main executable
Source: "dist\InfinityMetaHub.exe"; DestDir: "{app}"; \
  Flags: ignoreversion; DestName: "{#AppExeName}"

; Logo image (shown in the app folder too)
Source: "ayamil.jpg"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExeName}"; \
  Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; ============================================================
; Pascal script — upgrade detection + custom wizard pages
; ============================================================
[Code]

const
  NEW_VERSION   = '4.0.0';
  PREV_VERSION  = '2.0.0';     // last known shipped version (for display)

var
  // Page references
  PageAbout:   TWizardPage;
  PageWallet:  TWizardPage;

  // Controls on the About page
  LblAppTitle:    TLabel;
  LblDevBy:       TLabel;
  LblDesc:        TLabel;
  LblVersion:     TLabel;
  LblSocialTitle: TLabel;
  LblFacebook:    TLabel;
  LblInstagram:   TLabel;

  // Controls on the Wallet page
  LblWalletInfo:  TLabel;
  LblFromAddr:    TLabel;
  EdtFromAddr:    TEdit;
  LblPKNote:      TLabel;

  // Upgrade-mode flag
  IsUpgradeMode: Boolean;

// ── Helpers ───────────────────────────────────────────────────────────

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

// ── Detect existing installation ──────────────────────────────────────
//
// Inno Setup stores the installed version in the registry under the
// AppId key automatically.  We read it here to decide whether this
// is a fresh install or an upgrade.
//
function GetInstalledVersion: string;
var
  RegKey: string;
  InstalledVer: string;
begin
  RegKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' +
            '{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1';
  InstalledVer := '';
  // Try HKLM 64-bit first, then 32-bit hive
  if not RegQueryStringValue(HKLM64, RegKey, 'DisplayVersion', InstalledVer) then
    if not RegQueryStringValue(HKLM32, RegKey, 'DisplayVersion', InstalledVer) then
      RegQueryStringValue(HKCU, RegKey, 'DisplayVersion', InstalledVer);
  Result := InstalledVer;
end;

function PreviousInstallExists: Boolean;
begin
  Result := GetInstalledVersion <> '';
end;

// ── InitializeSetup: decide upgrade vs fresh-install ─────────────────
//
// Called before the wizard is shown.  We set the global flag and
// optionally show a confirmation dialog when upgrading.
//
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
           'New version       : ' + NEW_VERSION + #13#10 + #13#10 +
           'Click OK to upgrade, or Cancel to quit.';
    if MsgBox(Msg, mbConfirmation, MB_OKCANCEL) = IDCANCEL then
      Result := False;
  end;
end;

// ── Build wizard pages ────────────────────────────────────────────────
procedure InitializeWizard;
var
  AboutCaption: string;
  AboutSubCaption: string;
  DescText: string;
  OldVer: string;
begin
  OldVer := GetInstalledVersion;

  // ── Dynamic captions based on upgrade vs fresh install ───────────
  if IsUpgradeMode then
  begin
    AboutCaption    := 'Upgrading {#AppName} to v' + NEW_VERSION;
    AboutSubCaption := 'Developed by {#AppPublisher}  |  Upgrade from v' + OldVer;
    DescText :=
      'You are upgrading from v' + OldVer + ' to v' + NEW_VERSION + '.' + #13#10 + #13#10 +
      'What''s new in v' + NEW_VERSION + ':' + #13#10 +
      ' • All existing settings and wallet config are preserved' + #13#10 +
      ' • Improved stability and performance' + #13#10 +
      ' • Updated on-chain transaction logic' + #13#10 +
      ' • UI refresh and bug fixes' + #13#10 + #13#10 +
      'Current features:' + #13#10 +
      ' • View all withdrawal requests with real-time status' + #13#10 +
      ' • Approve or reject pending withdrawals' + #13#10 +
      ' • Automatic BH / USDT token transfers on Polygon & BSC' + #13#10 +
      ' • Multi-network wallet balance viewer (Polygon 137 + BSC 56)' + #13#10 +
      ' • Double-payment protection — prevents duplicate on-chain sends' + #13#10 +
      ' • Encrypted private-key storage with passphrase' + #13#10 +
      ' • Simulation mode for safe testing before going live';
  end
  else
  begin
    AboutCaption    := 'Welcome to {#AppName}';
    AboutSubCaption := 'Developed by {#AppPublisher}';
    DescText :=
      'A professional admin tool for managing on-chain withdrawal requests.' + #13#10 + #13#10 +
      'Features:' + #13#10 +
      ' • View all withdrawal requests with real-time status' + #13#10 +
      ' • Approve or reject pending withdrawals' + #13#10 +
      ' • Automatic BH / USDT token transfers on Polygon & BSC' + #13#10 +
      ' • Multi-network wallet balance viewer (Polygon 137 + BSC 56)' + #13#10 +
      ' • Double-payment protection — prevents duplicate on-chain sends' + #13#10 +
      ' • Encrypted private-key storage with passphrase' + #13#10 +
      ' • Simulation mode for safe testing before going live';
  end;

  // ────────────────────────────────────────────────────────────────
  // PAGE 1 — About / Upgrade info
  // ────────────────────────────────────────────────────────────────
  PageAbout := CreateCustomPage(
    wpWelcome,
    AboutCaption,
    AboutSubCaption
  );

  // App title
  LblAppTitle := TLabel.Create(PageAbout);
  with LblAppTitle do
  begin
    Parent    := PageAbout.Surface;
    Caption   := '{#AppName}  v' + NEW_VERSION;
    Font.Size := 18;
    Font.Style:= [fsBold];
    Font.Color:= clGreen;
    Left      := 0;
    Top       := 0;
    AutoSize  := True;
  end;

  // Developer credit
  LblDevBy := TLabel.Create(PageAbout);
  with LblDevBy do
  begin
    Parent    := PageAbout.Surface;
    Caption   := 'Developed by {#AppPublisher}';
    Font.Size := 10;
    Font.Color:= clGray;
    Left      := 0;
    Top       := 34;
    AutoSize  := True;
  end;

  // Version badge
  LblVersion := TLabel.Create(PageAbout);
  with LblVersion do
  begin
    Parent    := PageAbout.Surface;
    if IsUpgradeMode then
      Caption := '  UPGRADE: v' + OldVer + '  →  v' + NEW_VERSION + '  '
    else
      Caption := '  NEW INSTALL  v' + NEW_VERSION + '  ';
    Font.Size := 9;
    Font.Style:= [fsBold];
    if IsUpgradeMode then
      Font.Color:= clBlue
    else
      Font.Color:= clGreen;
    Left      := 0;
    Top       := 56;
    AutoSize  := True;
  end;

  // Description / changelog
  LblDesc := TLabel.Create(PageAbout);
  with LblDesc do
  begin
    Parent   := PageAbout.Surface;
    Caption  := DescText;
    Font.Size:= 9;
    Left     := 0;
    Top      := 82;
    Width    := 440;
    AutoSize := False;
    Height   := 170;
    WordWrap := True;
  end;

  // Social media section
  LblSocialTitle := TLabel.Create(PageAbout);
  with LblSocialTitle do
  begin
    Parent    := PageAbout.Surface;
    Caption   := 'Follow Ayamil Coders:';
    Font.Size := 9;
    Font.Style:= [fsBold];
    Left      := 0;
    Top       := 262;
    AutoSize  := True;
  end;

  LblFacebook := TLabel.Create(PageAbout);
  with LblFacebook do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '  Facebook: facebook.com/ayamilcoders';
    Font.Color := clBlue;
    Font.Style := [fsUnderline];
    Cursor     := crHand;
    Left       := 0;
    Top        := 284;
    AutoSize   := True;
    OnClick    := @OnFacebookClick;
  end;

  LblInstagram := TLabel.Create(PageAbout);
  with LblInstagram do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '  Instagram: instagram.com/ayamilcoders';
    Font.Color := clPurple;
    Font.Style := [fsUnderline];
    Cursor     := crHand;
    Left       := 0;
    Top        := 308;
    AutoSize   := True;
    OnClick    := @OnInstagramClick;
  end;

  // ────────────────────────────────────────────────────────────────
  // PAGE 2 — Wallet Setup
  // (skipped / read-only when upgrading so existing config is kept)
  // ────────────────────────────────────────────────────────────────
  PageWallet := CreateCustomPage(
    PageAbout.ID,
    'Wallet Setup',
    'Pre-configure your sending wallet (you can change this inside the app later)'
  );

  LblWalletInfo := TLabel.Create(PageWallet);
  with LblWalletInfo do
  begin
    Parent   := PageWallet.Surface;
    if IsUpgradeMode then
      Caption :=
        'You are upgrading an existing installation.' + #13#10 + #13#10 +
        'Your wallet settings are already saved in:' + #13#10 +
        '  %APPDATA%\.withdrawal_admin\config.json' + #13#10 + #13#10 +
        'No changes are needed here — click Next to continue.' + #13#10 +
        'You can update wallet settings inside the app after launch.'
    else
      Caption :=
        'Enter the wallet address that will send USDT / BH tokens to customers.' + #13#10 +
        'This wallet must hold:' + #13#10 +
        '  • MATIC (for gas fees on Polygon), or BNB (for gas on BSC)' + #13#10 +
        '  • Enough BH or USDT tokens to cover the pending withdrawals';
    Font.Size:= 9;
    Left     := 0;
    Top      := 0;
    Width    := 460;
    Height   := 100;
    AutoSize := False;
    WordWrap := True;
  end;

  LblFromAddr := TLabel.Create(PageWallet);
  with LblFromAddr do
  begin
    Parent    := PageWallet.Surface;
    Caption   := 'From Wallet Address:';
    Font.Size := 9;
    Font.Style:= [fsBold];
    Left      := 0;
    Top       := 110;
    AutoSize  := True;
    // Hide on upgrade — config already exists
    Visible   := not IsUpgradeMode;
  end;

  EdtFromAddr := TEdit.Create(PageWallet);
  with EdtFromAddr do
  begin
    Parent    := PageWallet.Surface;
    Text      := '';
    Left      := 0;
    Top       := 132;
    Width     := 460;
    Font.Name := 'Consolas';
    Font.Size := 9;
    // Hide on upgrade
    Visible   := not IsUpgradeMode;
    Enabled   := not IsUpgradeMode;
  end;

  LblPKNote := TLabel.Create(PageWallet);
  with LblPKNote do
  begin
    Parent   := PageWallet.Surface;
    if IsUpgradeMode then
      Caption :=
        '✔ Upgrade preserves your encrypted private key.' + #13#10 +
        'You will NOT need to re-enter it.' + #13#10 + #13#10 +
        'Click Next to proceed with the installation.'
    else
      Caption :=
        '⚠ Your PRIVATE KEY is NOT entered here.' + #13#10 +
        'You will enter it securely inside the app after installation.' + #13#10 +
        'The app encrypts it with a passphrase of your choice and never' + #13#10 +
        'stores it in plain text.' + #13#10 + #13#10 +
        'You can skip this page — the wallet address can also be set' + #13#10 +
        'in Wallet & API Settings after the app opens.';
    Font.Size := 9;
    if IsUpgradeMode then
      Font.Color := clGreen
    else
      Font.Color := clGreen;
    Left     := 0;
    Top      := 172;
    Width    := 460;
    Height   := 140;
    AutoSize := False;
    WordWrap := True;
  end;
end;

// ── Write initial config (fresh install only) ─────────────────────────
procedure WriteInitialConfig(const FromAddress: string);
var
  ConfigDir:  string;
  ConfigPath: string;
  ConfigJson: string;
begin
  ConfigDir  := ExpandConstant('{userappdata}') + '\.withdrawal_admin';
  ConfigPath := ConfigDir + '\config.json';

  // Never overwrite an existing config — upgrade keeps user settings
  if FileExists(ConfigPath) then
    Exit;

  if not DirExists(ConfigDir) then
    CreateDir(ConfigDir);

  ConfigJson :=
    '{' + #13#10 +
    '  "api_base_url": "https://yourdomain.com/api/v1/admin/withdrawals",' + #13#10 +
    '  "auth_header": "",' + #13#10 +
    '  "network": "polygon_bh",' + #13#10 +
    '  "rpc_url": "https://polygon-rpc.com",' + #13#10 +
    '  "token_contract": "0x68a6EA8e9aB0824251061DD122aDA8493e62409d",' + #13#10 +
    '  "decimals": 18,' + #13#10 +
    '  "amount_source": "bh",' + #13#10 +
    '  "from_address": "' + FromAddress + '",' + #13#10 +
    '  "simulate_only": true,' + #13#10 +
    '  "pk_set": false,' + #13#10 +
    '  "pk_salt": "",' + #13#10 +
    '  "pk_token": "",' + #13#10 +
    '  "extra_tokens": [],' + #13#10 +
    '  "app_version": "' + NEW_VERSION + '"' + #13#10 +
    '}';

  SaveStringToFile(ConfigPath, ConfigJson, False);
end;

// ── Update version field in existing config on upgrade ────────────────
procedure UpdateConfigVersion;
var
  ConfigPath: string;
  OldContent: string;
  NewContent: string;
  VerLine:    string;
begin
  ConfigPath := ExpandConstant('{userappdata}') + '\.withdrawal_admin\config.json';
  if not FileExists(ConfigPath) then
    Exit;

  if not LoadStringFromFile(ConfigPath, OldContent) then
    Exit;

  // Remove old version line if present, append updated one
  // Simple approach: replace the version value via string search
  VerLine := '"app_version": "' + NEW_VERSION + '"';
  // If old version key exists with a different value, replace it
  // We can't do regex in Pascal so we just check and append if missing
  if Pos('"app_version"', OldContent) = 0 then
  begin
    // Append before last closing brace
    NewContent := Copy(OldContent, 1, Length(OldContent) - 1);
    // Remove trailing whitespace/newlines before }
    while (Length(NewContent) > 0) and
          ((NewContent[Length(NewContent)] = ' ') or
           (NewContent[Length(NewContent)] = #13) or
           (NewContent[Length(NewContent)] = #10)) do
      Delete(NewContent, Length(NewContent), 1);
    NewContent := NewContent + ',' + #13#10 +
                  '  ' + VerLine + #13#10 + '}';
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

// ── Validation on Next ────────────────────────────────────────────────
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = PageWallet.ID then
  begin
    // On upgrade the wallet page is informational only — always pass
    if IsUpgradeMode then
      Exit;

    // Fresh install: validate address format if provided
    if (Length(EdtFromAddr.Text) > 0) and
       (Length(EdtFromAddr.Text) < 42) then
    begin
      MsgBox(
        'Wallet address looks too short. A valid Ethereum/Polygon address' + #13#10 +
        'starts with "0x" and is 42 characters long.' + #13#10 + #13#10 +
        'You can leave it blank and set it in the app later.',
        mbInformation, MB_OK
      );
      // Don't block — let the user proceed anyway
    end;
  end;
end;

// ── Customize the "Ready to Install / Update" button label ───────────
procedure CurPageChanged(CurPageID: Integer);
begin
  // When we reach the ready-to-install page, relabel the button
  // to "Update" if we are upgrading.
  if IsUpgradeMode and (CurPageID = wpReady) then
    WizardForm.NextButton.Caption := '&Update';
end;
