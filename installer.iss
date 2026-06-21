; ============================================================
;  Infinity Meta Hub — Windows Installer
;  Version 4.0.0
;  Built with Inno Setup 6
;  Developed by Ayamil Coders
; ============================================================

#define AppName      "Infinity Meta Hub"
#define AppVersion   "4.0.0"
#define AppPublisher "Ayamil Coders"
#define AppExeName   "InfinityMetaHub.exe"
#define AppURL       "https://www.facebook.com/ayamilcoders"
#define AppRegKey    "Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1"

[Setup]
; IMPORTANT: Keep this AppId the same across versions so Windows recognises
; this as an upgrade of the same product (not a new install).
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

; Wizard images converted from ayamil.jpg by build.yml
WizardImageFile=ayamil_banner.bmp
WizardSmallImageFile=ayamil_small.bmp
SetupIconFile=imh.ico
WizardStyle=modern

OutputDir=dist_installer
OutputBaseFilename=InfinityMetaHub_Setup_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes

UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Allow upgrade install without asking to uninstall first
; The old version is automatically replaced.
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

PrivilegesRequired=admin
ShowLanguageDialog=no
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

; Upgrade behaviour:
;   - Files are always overwritten on upgrade
;   - User config (~/.withdrawal_admin/config.json) is preserved
;   - Desktop shortcut is preserved
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
  Description: "Create a &desktop shortcut"; \
  GroupDescription: "Shortcuts:"; \
  Flags: checkedonce

[Files]
Source: "dist\InfinityMetaHub.exe"; DestDir: "{app}"; \
  Flags: ignoreversion; DestName: "{#AppExeName}"
Source: "ayamil.jpg";       DestDir: "{app}"; Flags: ignoreversion
Source: "imh.png";          DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "imh.ico";          DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";   Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExeName}"; \
  Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; ============================================================
;  Pascal script
; ============================================================
[Code]

// ── Globals ──────────────────────────────────────────────────────────
var
  IsUpgrade:         Boolean;
  InstalledVersion:  string;

  // Custom pages
  PageAbout:   TWizardPage;
  PageWallet:  TWizardPage;

  // About page controls
  LblAppTitle:    TLabel;
  LblDevBy:       TLabel;
  LblVersion:     TLabel;
  LblDesc:        TLabel;
  LblSocialTitle: TLabel;
  LblFacebook:    TLabel;
  LblInstagram:   TLabel;
  LblUpgradeBanner: TLabel;

  // Wallet page controls
  LblWalletInfo: TLabel;
  LblFromAddr:   TLabel;
  EdtFromAddr:   TEdit;
  LblPKNote:     TLabel;

// ── Helpers ───────────────────────────────────────────────────────────
procedure OpenURL(const URL: string);
var ErrCode: Integer;
begin
  ShellExec('open', URL, '', '', SW_SHOWNORMAL, ewNoWait, ErrCode);
end;

procedure OnFacebookClick(Sender: TObject);
begin OpenURL('https://www.facebook.com/ayamilcoders'); end;

procedure OnInstagramClick(Sender: TObject);
begin OpenURL('https://www.instagram.com/ayamilcoders'); end;

// ── Detect existing install ───────────────────────────────────────────
function GetInstalledVersion: string;
var
  Ver: string;
begin
  Result := '';
  if RegQueryStringValue(HKLM,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1',
      'DisplayVersion', Ver) then
    Result := Ver
  else if RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1',
      'DisplayVersion', Ver) then
    Result := Ver;
end;

// Version compare: returns true if V1 < V2 (upgrade scenario)
function VersionLessThan(const V1, V2: string): Boolean;
var
  P1, P2: array[0..3] of Integer;
  Parts1, Parts2: TStringList;
  i: Integer;
begin
  Parts1 := TStringList.Create;
  Parts2 := TStringList.Create;
  try
    Parts1.Delimiter     := '.';
    Parts1.DelimitedText := V1;
    Parts2.Delimiter     := '.';
    Parts2.DelimitedText := V2;
    for i := 0 to 3 do
    begin
      if i < Parts1.Count then P1[i] := StrToIntDef(Parts1[i], 0) else P1[i] := 0;
      if i < Parts2.Count then P2[i] := StrToIntDef(Parts2[i], 0) else P2[i] := 0;
    end;
  finally
    Parts1.Free;
    Parts2.Free;
  end;
  for i := 0 to 3 do
  begin
    if P1[i] < P2[i] then begin Result := True;  Exit; end;
    if P1[i] > P2[i] then begin Result := False; Exit; end;
  end;
  Result := False; // equal
end;

// ── Build wizard pages ────────────────────────────────────────────────
procedure InitializeWizard;
var
  BannerBg: Integer;
begin
  InstalledVersion := GetInstalledVersion;
  IsUpgrade        := (InstalledVersion <> '') and
                      VersionLessThan(InstalledVersion, '{#AppVersion}');

  BannerBg := $00237E1A; // dark green

  // ────────────────────────────────────────────────────────────────────
  // PAGE 1 — About / Upgrade notice
  // ────────────────────────────────────────────────────────────────────
  PageAbout := CreateCustomPage(
    wpWelcome,
    'Welcome to {#AppName}',
    'Developed by {#AppPublisher}'
  );

  // ── Upgrade banner (visible only when upgrading) ──────────────────
  LblUpgradeBanner := TLabel.Create(PageAbout);
  with LblUpgradeBanner do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '';
    Font.Size  := 9;
    Font.Style := [fsBold];
    Font.Color := $000000CC; // red-ish
    Left   := 0;
    Top    := 0;
    Width  := 460;
    Height := 26;
    Visible   := IsUpgrade;
    WordWrap  := True;
    AutoSize  := False;
  end;

  if IsUpgrade then
    LblUpgradeBanner.Caption :=
      'UPDATE DETECTED:  v' + InstalledVersion + '  →  v{#AppVersion}' +
      '   Your settings and config will be preserved.';

  // ── App title ─────────────────────────────────────────────────────
  LblAppTitle := TLabel.Create(PageAbout);
  with LblAppTitle do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '{#AppName}';
    Font.Size  := 20;
    Font.Style := [fsBold];
    Font.Color := BannerBg;
    Left     := 0;
    Top      := IfThen(IsUpgrade, 34, 0);
    AutoSize := True;
  end;

  // ── Version badge ─────────────────────────────────────────────────
  LblVersion := TLabel.Create(PageAbout);
  with LblVersion do
  begin
    Parent     := PageAbout.Surface;
    Caption    := 'Version {#AppVersion}';
    Font.Size  := 9;
    Font.Color := $00888888;
    Left     := 0;
    Top      := LblAppTitle.Top + 36;
    AutoSize := True;
  end;

  // ── Developer credit ──────────────────────────────────────────────
  LblDevBy := TLabel.Create(PageAbout);
  with LblDevBy do
  begin
    Parent     := PageAbout.Surface;
    Caption    := 'Developed by {#AppPublisher}';
    Font.Size  := 9;
    Font.Style := [fsBold];
    Font.Color := $00555555;
    Left     := 0;
    Top      := LblVersion.Top + 20;
    AutoSize := True;
  end;

  // ── Feature list ──────────────────────────────────────────────────
  LblDesc := TLabel.Create(PageAbout);
  with LblDesc do
  begin
    Parent   := PageAbout.Surface;
    Caption  :=
      'A professional admin tool for managing on-chain withdrawal requests.' +
      #13#10 + #13#10 +
      'What''s new in v4.0:' + #13#10 +
      '  *  Double-payment protection with persistent TX store' + #13#10 +
      '  *  Wallet Balances tab scans Polygon (137) + BSC (56) together' + #13#10 +
      '  *  Multi-RPC fallback — auto-retries on different endpoints' + #13#10 +
      '  *  Upgrade installer — preserves your settings on update' + #13#10 +
      #13#10 +
      'All features:' + #13#10 +
      '  *  Approve / reject withdrawals with on-chain BH / USDT transfer' + #13#10 +
      '  *  Activity log with clickable block-explorer links' + #13#10 +
      '  *  Encrypted private-key storage (PBKDF2 + Fernet)' + #13#10 +
      '  *  Simulation mode for safe testing before going live';
    Font.Size := 9;
    Left     := 0;
    Top      := LblDevBy.Top + 22;
    Width    := 450;
    Height   := 200;
    AutoSize := False;
    WordWrap := True;
  end;

  // ── Social links ──────────────────────────────────────────────────
  LblSocialTitle := TLabel.Create(PageAbout);
  with LblSocialTitle do
  begin
    Parent     := PageAbout.Surface;
    Caption    := 'Follow Ayamil Coders:';
    Font.Size  := 9;
    Font.Style := [fsBold];
    Left     := 0;
    Top      := LblDesc.Top + 208;
    AutoSize := True;
  end;

  LblFacebook := TLabel.Create(PageAbout);
  with LblFacebook do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '   Facebook:   facebook.com/ayamilcoders';
    Font.Color := clBlue;
    Font.Style := [fsUnderline];
    Cursor     := crHand;
    Left     := 0;
    Top      := LblSocialTitle.Top + 22;
    AutoSize := True;
    OnClick  := @OnFacebookClick;
  end;

  LblInstagram := TLabel.Create(PageAbout);
  with LblInstagram do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '   Instagram:  instagram.com/ayamilcoders';
    Font.Color := $00A01CC5;
    Font.Style := [fsUnderline];
    Cursor     := crHand;
    Left     := 0;
    Top      := LblFacebook.Top + 22;
    AutoSize := True;
    OnClick  := @OnInstagramClick;
  end;

  // ────────────────────────────────────────────────────────────────────
  // PAGE 2 — Wallet Setup
  // (skipped on upgrade if address already in config.json)
  // ────────────────────────────────────────────────────────────────────
  PageWallet := CreateCustomPage(
    PageAbout.ID,
    'Wallet Setup',
    'Pre-configure your sending wallet (you can change this in the app later)'
  );

  LblWalletInfo := TLabel.Create(PageWallet);
  with LblWalletInfo do
  begin
    Parent   := PageWallet.Surface;
    Caption  :=
      'Enter the wallet address that will send USDT / BH tokens to customers.' +
      #13#10 +
      'This wallet must hold:' + #13#10 +
      '  *  MATIC (gas on Polygon) or BNB (gas on BSC)' + #13#10 +
      '  *  Enough BH or USDT tokens to cover the pending withdrawals' +
      #13#10 + #13#10 +
      'On upgrade your existing wallet address is already saved — ' +
      'leave this blank to keep it.';
    Font.Size := 9;
    Left  := 0;
    Top   := 0;
    Width := 460;
    Height:= 110;
    AutoSize := False;
    WordWrap := True;
  end;

  LblFromAddr := TLabel.Create(PageWallet);
  with LblFromAddr do
  begin
    Parent     := PageWallet.Surface;
    Caption    := 'From Wallet Address  (optional on upgrade):';
    Font.Size  := 9;
    Font.Style := [fsBold];
    Left     := 0;
    Top      := 118;
    AutoSize := True;
  end;

  EdtFromAddr := TEdit.Create(PageWallet);
  with EdtFromAddr do
  begin
    Parent    := PageWallet.Surface;
    Text      := '';
    Left      := 0;
    Top       := 140;
    Width     := 460;
    Font.Name := 'Consolas';
    Font.Size := 9;
  end;

  LblPKNote := TLabel.Create(PageWallet);
  with LblPKNote do
  begin
    Parent   := PageWallet.Surface;
    Caption  :=
      'WARNING: Your PRIVATE KEY is NOT entered here.' + #13#10 +
      'Enter it securely inside the app after installation.' + #13#10 +
      'The app encrypts it with a passphrase — it is never stored in plain text.';
    Font.Size  := 9;
    Font.Color := $00006614;
    Left  := 0;
    Top   := 178;
    Width := 460;
    Height:= 80;
    AutoSize := False;
    WordWrap := True;
  end;
end;

// ── Skip wallet page on upgrade (settings already exist) ─────────────
function ShouldSkipPage(PageID: Integer): Boolean;
var ConfigPath: string;
begin
  Result := False;
  if PageID = PageWallet.ID then
  begin
    // Skip wallet page if config.json already has a from_address set
    ConfigPath := ExpandConstant('{userappdata}') +
                  '\.withdrawal_admin\config.json';
    if IsUpgrade and FileExists(ConfigPath) then
      Result := True;
  end;
end;

// ── Write initial config (only on fresh install, not upgrade) ─────────
procedure WriteInitialConfig(const FromAddress: string);
var
  ConfigDir:  string;
  ConfigPath: string;
  ConfigJson: string;
begin
  ConfigDir  := ExpandConstant('{userappdata}') + '\.withdrawal_admin';
  ConfigPath := ConfigDir + '\config.json';

  // On upgrade: only update from_address if user actually typed one
  if IsUpgrade then
  begin
    // Don't touch config on upgrade — preserve all user settings
    Exit;
  end;

  // Fresh install: write default config if it doesn't exist yet
  if FileExists(ConfigPath) then
    Exit;

  if not DirExists(ConfigDir) then
    CreateDir(ConfigDir);

  ConfigJson :=
    '{' + #13#10 +
    '  "api_base_url":   "https://yourdomain.com/api/v1/admin/withdrawals",' + #13#10 +
    '  "auth_header":    "",' + #13#10 +
    '  "network":        "polygon_bh",' + #13#10 +
    '  "rpc_url":        "https://polygon-rpc.com",' + #13#10 +
    '  "token_contract": "0x68a6EA8e9aB0824251061DD122aDA8493e62409d",' + #13#10 +
    '  "decimals":       18,' + #13#10 +
    '  "amount_source":  "bh",' + #13#10 +
    '  "from_address":   "' + FromAddress + '",' + #13#10 +
    '  "simulate_only":  true,' + #13#10 +
    '  "pk_set":         false,' + #13#10 +
    '  "pk_salt":        "",' + #13#10 +
    '  "pk_token":       "",' + #13#10 +
    '  "extra_tokens":   []' + #13#10 +
    '}';

  SaveStringToFile(ConfigPath, ConfigJson, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteInitialConfig(EdtFromAddr.Text);
end;

// ── Upgrade confirmation prompt ───────────────────────────────────────
function InitializeSetup: Boolean;
begin
  Result            := True;
  InstalledVersion  := GetInstalledVersion;
  IsUpgrade         := (InstalledVersion <> '') and
                       VersionLessThan(InstalledVersion, '{#AppVersion}');

  if IsUpgrade then
  begin
    if MsgBox(
      '{#AppName}' + #13#10 + #13#10 +
      'An older version (v' + InstalledVersion + ') is already installed.' +
      #13#10 + #13#10 +
      'This will UPDATE to v{#AppVersion}.' + #13#10 +
      'Your settings and wallet config will be preserved.' + #13#10 + #13#10 +
      'Click YES to update, or NO to cancel.',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end
  else if InstalledVersion = '{#AppVersion}' then
  begin
    // Same version already installed — ask if they want to reinstall
    if MsgBox(
      '{#AppName} v{#AppVersion} is already installed.' + #13#10 + #13#10 +
      'Do you want to reinstall it? Your settings will be preserved.',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;

// ── Validation on Next ────────────────────────────────────────────────
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PageWallet.ID then
  begin
    if (Length(EdtFromAddr.Text) > 0) and (Length(EdtFromAddr.Text) < 42) then
      MsgBox(
        'Wallet address looks too short.' + #13#10 +
        'A valid Ethereum/Polygon address starts with "0x" and is 42 chars.' +
        #13#10 + #13#10 +
        'You can leave it blank and set it inside the app.',
        mbInformation, MB_OK);
  end;
end;
