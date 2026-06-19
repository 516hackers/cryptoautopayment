; ============================================================
;  Infinity Meta Hub — Windows Installer
;  Built with Inno Setup 6
;  Developed by Ayamil Coders
; ============================================================

#define AppName      "Infinity Meta Hub"
#define AppVersion   "2.0.0"
#define AppPublisher "Ayamil Coders"
#define AppExeName   "InfinityMetaHub.exe"
#define AppURL       "https://www.facebook.com/ayamilcoders"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
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
; Wizard images are generated from ayamil.jpg by build.yml:
; ayamil_banner.bmp (164x314) and ayamil_small.bmp (55x58)
WizardImageFile=ayamil_banner.bmp
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
Name: "{group}\{#AppName}";                   Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";         Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";             Filename: "{app}\{#AppExeName}"; \
  Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; ============================================================
;  Pascal script — custom wizard pages
; ============================================================
[Code]

var
  // Page references
  PageAbout:        TWizardPage;
  PageWallet:       TWizardPage;

  // Controls on the About page
  LblAppTitle:      TLabel;
  LblDevBy:         TLabel;
  LblDesc:          TLabel;
  LblSocialTitle:   TLabel;
  LblFacebook:      TLabel;
  LblInstagram:     TLabel;

  // Controls on the Wallet page
  LblWalletInfo:    TLabel;
  LblFromAddr:      TLabel;
  EdtFromAddr:      TEdit;
  LblPKNote:        TLabel;

// ── URL opener ────────────────────────────────────────────────────────
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

// ── Build wizard pages ────────────────────────────────────────────────
procedure InitializeWizard;
begin
  // ──────────────────────────────────────────────────────────────────
  // PAGE 1 — About Ayamil Coders
  // ──────────────────────────────────────────────────────────────────
  PageAbout := CreateCustomPage(
    wpWelcome,
    'Welcome to ' + '{#AppName}',
    'Developed by {#AppPublisher}'
  );

  // App title
  LblAppTitle := TLabel.Create(PageAbout);
  with LblAppTitle do
  begin
    Parent    := PageAbout.Surface;
    Caption   := '{#AppName}';
    Font.Size := 20;
    Font.Style:= [fsBold];
    Font.Color:= $00237E1A;
    Left := 0;
    Top  := 0;
    AutoSize := True;
  end;

  // Developer credit
  LblDevBy := TLabel.Create(PageAbout);
  with LblDevBy do
  begin
    Parent    := PageAbout.Surface;
    Caption   := 'Developed by {#AppPublisher}';
    Font.Size := 10;
    Font.Color:= $00555555;
    Left := 0;
    Top  := 36;
    AutoSize := True;
  end;

  // Description
  LblDesc := TLabel.Create(PageAbout);
  with LblDesc do
  begin
    Parent    := PageAbout.Surface;
    Caption   :=
      'A professional admin tool for managing on-chain withdrawal requests.' + #13#10 + #13#10 +
      'Features:' + #13#10 +
      '  •  View all withdrawal requests with real-time status' + #13#10 +
      '  •  Approve or reject pending withdrawals' + #13#10 +
      '  •  Automatic BH / USDT token transfers on Polygon & BSC' + #13#10 +
      '  •  Multi-network wallet balance viewer (Polygon 137 + BSC 56)' + #13#10 +
      '  •  Double-payment protection — prevents duplicate on-chain sends' + #13#10 +
      '  •  Encrypted private-key storage with passphrase' + #13#10 +
      '  •  Simulation mode for safe testing before going live';
    Font.Size := 9;
    Left  := 0;
    Top   := 62;
    Width := 440;
    AutoSize := False;
    Height   := 180;
    WordWrap := True;
  end;

  // Social media section
  LblSocialTitle := TLabel.Create(PageAbout);
  with LblSocialTitle do
  begin
    Parent   := PageAbout.Surface;
    Caption  := 'Follow Ayamil Coders:';
    Font.Size:= 9;
    Font.Style:=[fsBold];
    Left := 0;
    Top  := 258;
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
    Left := 0;
    Top  := 282;
    AutoSize  := True;
    OnClick   := @OnFacebookClick;
  end;

  LblInstagram := TLabel.Create(PageAbout);
  with LblInstagram do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '   Instagram:  instagram.com/ayamilcoders';
    Font.Color := $00A01CC5;   // Instagram purple
    Font.Style := [fsUnderline];
    Cursor     := crHand;
    Left := 0;
    Top  := 308;
    AutoSize  := True;
    OnClick   := @OnInstagramClick;
  end;

  // ──────────────────────────────────────────────────────────────────
  // PAGE 2 — Wallet Setup
  // ──────────────────────────────────────────────────────────────────
  PageWallet := CreateCustomPage(
    PageAbout.ID,
    'Wallet Setup',
    'Pre-configure your sending wallet (you can change this inside the app later)'
  );

  LblWalletInfo := TLabel.Create(PageWallet);
  with LblWalletInfo do
  begin
    Parent   := PageWallet.Surface;
    Caption  :=
      'Enter the wallet address that will send USDT / BH tokens to customers.' + #13#10 +
      'This wallet must hold:' + #13#10 +
      '  •  MATIC (for gas fees on Polygon), or BNB (for gas on BSC)' + #13#10 +
      '  •  Enough BH or USDT tokens to cover the pending withdrawals';
    Font.Size:= 9;
    Left  := 0;
    Top   := 0;
    Width := 460;
    Height:= 80;
    AutoSize := False;
    WordWrap := True;
  end;

  LblFromAddr := TLabel.Create(PageWallet);
  with LblFromAddr do
  begin
    Parent   := PageWallet.Surface;
    Caption  := 'From Wallet Address:';
    Font.Size:= 9;
    Font.Style:=[fsBold];
    Left := 0;
    Top  := 92;
    AutoSize := True;
  end;

  EdtFromAddr := TEdit.Create(PageWallet);
  with EdtFromAddr do
  begin
    Parent   := PageWallet.Surface;
    Text     := '';
    Left     := 0;
    Top      := 116;
    Width    := 460;
    Font.Name:= 'Consolas';
    Font.Size:= 9;
  end;

  LblPKNote := TLabel.Create(PageWallet);
  with LblPKNote do
  begin
    Parent   := PageWallet.Surface;
    Caption  :=
      '⚠  Your PRIVATE KEY is NOT entered here.' + #13#10 +
      'You will enter it securely inside the app after installation.' + #13#10 +
      'The app encrypts it with a passphrase of your choice and never' + #13#10 +
      'stores it in plain text.' + #13#10 + #13#10 +
      'You can skip this page — the wallet address can also be set' + #13#10 +
      'in  Wallet & API Settings  after the app opens.';
    Font.Size := 9;
    Font.Color:= $00006614;
    Left  := 0;
    Top   := 154;
    Width := 460;
    Height:= 140;
    AutoSize := False;
    WordWrap := True;
  end;
end;

// ── Write initial config after install ───────────────────────────────
procedure WriteInitialConfig(const FromAddress: string);
var
  ConfigDir:  string;
  ConfigPath: string;
  ConfigJson: string;
begin
  ConfigDir  := ExpandConstant('{userappdata}') + '\.withdrawal_admin';
  ConfigPath := ConfigDir + '\config.json';

  // Only write if the file does not already exist
  // (don't overwrite existing user config on reinstall)
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

// ── Validation on Next ────────────────────────────────────────────────
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = PageWallet.ID then
  begin
    // From address is optional — just validate format if provided
    if (Length(EdtFromAddr.Text) > 0) and
       (Length(EdtFromAddr.Text) < 42) then
    begin
      MsgBox(
        'Wallet address looks too short. A valid Ethereum/Polygon address' + #13#10 +
        'starts with "0x" and is 42 characters long.' + #13#10 + #13#10 +
        'You can leave it blank and set it in the app later.',
        mbInformation, MB_OK
      );
      // Don't block — let the user continue anyway
    end;
  end;
end;
