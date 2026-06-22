; ============================================================
; Infinity Meta Hub — Windows Installer
; Built with Inno Setup 6
; Developed by Ayamil Coders
; Version 4.0
; ============================================================

#define AppName "Infinity Meta Hub"
#define AppVersion "4.0.1"
#define AppPublisher "Ayamil Coders"
#define AppExeName "InfinityMetaHub.exe"
#define AppURL "https://www.facebook.com/ayamilcoders"

[Setup]
; Use the same AppId to detect previous installations
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Default installation directory
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Wizard images are generated from ayamil.jpg by build.yml
WizardImageFile=ayamil_banner.bmp
WizardImageStretch=yes
WizardSmallImageFile=ayamil_small.bmp

; Application icon (favicon)
SetupIconFile=imh.ico

WizardStyle=modern
OutputDir=dist_installer
OutputBaseFilename=InfinityMetaHub_Setup_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; IMPORTANT: For update/upgrade support
PrivilegesRequired=admin
ShowLanguageDialog=no
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

; These flags enable update/upgrade behavior
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousLanguage=yes
DisableReadyPage=no
AlwaysRestart=no
DisableReadyMemo=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; Main executable - will overwrite existing
Source: "dist\InfinityMetaHub.exe"; DestDir: "{app}"; Flags: ignoreversion; DestName: "{#AppExeName}"

; Logo image - will overwrite existing
Source: "ayamil.jpg"; DestDir: "{app}"; Flags: ignoreversion

; Favicon image - will overwrite existing
Source: "imh.png"; DestDir: "{app}"; Flags: ignoreversion

; ICO file - will overwrite existing
Source: "imh.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

; ============================================================
; Pascal script — custom wizard pages with Update Detection
; ============================================================
[Code]

var
  // Page references
  PageAbout:         TWizardPage;
  PageWallet:        TWizardPage;
  PageUpdateOptions: TWizardPage;

  // Controls on the About page
  LblAppTitle:    TLabel;
  LblDevBy:       TLabel;
  LblDesc:        TLabel;
  LblSocialTitle: TLabel;
  LblFacebook:    TLabel;
  LblInstagram:   TLabel;

  // Controls on the Wallet page
  LblWalletInfo: TLabel;
  LblFromAddr:   TLabel;
  EdtFromAddr:   TEdit;
  LblPKNote:     TLabel;

  // Controls on the Update Options page
  LblUpdateVersions: TLabel;
  LblWhatsNewTitle:  TLabel;
  LblWhatsNew:       TLabel;
  LblChooseAction:   TLabel;
  RbUpdate:          TRadioButton;
  RbRepair:          TRadioButton;
  RbUninstallFirst:  TRadioButton;

  // Update/Upgrade detection
  IsUpdate:    Boolean;
  OldVersion:  String;
  UpdateChoice: Integer; // 0 = Update (default), 1 = Repair, 2 = Uninstall first

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

// ── Update Options radio button handlers ───────────────────────────────
procedure OnChooseUpdate(Sender: TObject);
begin
  UpdateChoice := 0;
end;

procedure OnChooseRepair(Sender: TObject);
begin
  UpdateChoice := 1;
end;

procedure OnChooseUninstallFirst(Sender: TObject);
begin
  UpdateChoice := 2;
end;

// ── Detect if this is an update/upgrade ────────────────────────────────
function IsUpgradeInstalled(): Boolean;
var
  UninstallKey:  String;
  OldVersionStr: String;
begin
  Result := False;
  OldVersion := '';

  // Inno Setup stores uninstall info under "<AppId>_is1"
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
                   '{#SetupSetting("AppId")}' + '_is1';

  if RegKeyExists(HKLM, UninstallKey) or RegKeyExists(HKCU, UninstallKey) then
  begin
    Result := True;

    // Try to get the old version
    if RegQueryStringValue(HKLM, UninstallKey, 'DisplayVersion', OldVersionStr) then
      OldVersion := OldVersionStr
    else if RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', OldVersionStr) then
      OldVersion := OldVersionStr;

    if OldVersion = '' then
      OldVersion := 'Unknown';
  end;
end;

// ── Locate the previous version's uninstaller ──────────────────────────
function GetPreviousUninstallString(): String;
var
  UninstallKey: String;
  US:           String;
begin
  Result := '';
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
                   '{#SetupSetting("AppId")}' + '_is1';

  if RegQueryStringValue(HKLM, UninstallKey, 'UninstallString', US) then
    Result := US
  else if RegQueryStringValue(HKCU, UninstallKey, 'UninstallString', US) then
    Result := US;
end;

// ── Run the previous version's uninstaller silently ────────────────────
function UninstallPreviousVersion(): Boolean;
var
  RawCmd, Exe: String;
  QuotePos:    Integer;
  ResultCode:  Integer;
begin
  Result := False;
  RawCmd := GetPreviousUninstallString();

  if RawCmd = '' then
  begin
    MsgBox('Could not find the previous version''s uninstaller in the registry.' + #13#10 +
           'Setup will continue as a normal update instead (existing settings will be kept).',
           mbInformation, MB_OK);
    UpdateChoice := 0;
    Result := True;
    Exit;
  end;

  // Strip surrounding quotes from the registry UninstallString
  Exe := RawCmd;
  if (Length(Exe) > 0) and (Exe[1] = '"') then
  begin
    Exe := Copy(Exe, 2, Length(Exe) - 1);
    QuotePos := Pos('"', Exe);
    if QuotePos > 0 then
      Exe := Copy(Exe, 1, QuotePos - 1);
  end;

  if not FileExists(Exe) then
  begin
    MsgBox('The previous uninstaller could not be found on disk:' + #13#10 + Exe + #13#10#13#10 +
           'Setup will continue as a normal update instead (existing settings will be kept).',
           mbInformation, MB_OK);
    UpdateChoice := 0;
    Result := True;
    Exit;
  end;

  if not Exec(Exe, '/VERYSILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_SHOW,
              ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('Could not launch the previous uninstaller.' + #13#10 +
           'Setup will continue as a normal update instead (existing settings will be kept).',
           mbError, MB_OK);
    UpdateChoice := 0;
    Result := True;
    Exit;
  end;

  Result := True;
end;

// ── Reset wallet/API config (used by Repair and Uninstall-first) ──────
procedure ResetConfigForRepair();
var
  ConfigDir, ConfigPath, PendingPath: String;
begin
  ConfigDir   := ExpandConstant('{userappdata}') + '\.withdrawal_admin';
  ConfigPath  := ConfigDir + '\config.json';
  PendingPath := ConfigDir + '\pending_tx.json';

  if FileExists(ConfigPath) then
    DeleteFile(ConfigPath);
  if FileExists(PendingPath) then
    DeleteFile(PendingPath);

  Log('Repair/reinstall selected: wallet & API config reset ' +
      '(transaction history and security logs were kept).');
end;

// ── Build wizard pages ───────────────────────────────────────────────
procedure InitializeWizard;
var
  WelcomeText: String;
  SubText:     String;
begin
  // Check if this is an update
  IsUpdate := IsUpgradeInstalled();
  UpdateChoice := 0;

  // Customize welcome page based on update status
  if IsUpdate then
  begin
    WelcomeText := 'Upgrading to ' + '{#AppName} v{#AppVersion}';
    SubText     := 'You are upgrading from version ' + OldVersion + ' to v{#AppVersion}';
  end
  else
  begin
    WelcomeText := 'Welcome to ' + '{#AppName} v{#AppVersion}';
    SubText     := 'Developed by {#AppPublisher}';
  end;

  // ────────────────────────────────────────────────────────────────
  // PAGE 1 — About Ayamil Coders
  // ────────────────────────────────────────────────────────────────
  PageAbout := CreateCustomPage(wpWelcome, WelcomeText, SubText);

  // App title
  LblAppTitle := TLabel.Create(PageAbout);
  with LblAppTitle do
  begin
    Parent     := PageAbout.Surface;
    Caption    := '{#AppName} v{#AppVersion}';
    Font.Size  := 20;
    Font.Style := [fsBold];
    Font.Color := $00237E1A;
    Left       := 0;
    Top        := 0;
    Width      := 460;
    Height     := 30;
  end;

  // Version info - show if update
  if IsUpdate then
  begin
    LblDevBy := TLabel.Create(PageAbout);
    with LblDevBy do
    begin
      Parent     := PageAbout.Surface;
      Caption    := 'Upgrading from v' + OldVersion + ' to v{#AppVersion}';
      Font.Size  := 10;
      Font.Color := $000000FF; // highlight color for update
      Left       := 0;
      Top        := 36;
      Width      := 460;
      Height     := 20;
    end;
  end
  else
  begin
    LblDevBy := TLabel.Create(PageAbout);
    with LblDevBy do
    begin
      Parent     := PageAbout.Surface;
      Caption    := 'Developed by {#AppPublisher}';
      Font.Size  := 10;
      Font.Color := $00555555;
      Left       := 0;
      Top        := 36;
      Width      := 460;
      Height     := 20;
    end;
  end;

  // Description
  LblDesc := TLabel.Create(PageAbout);
  with LblDesc do
  begin
    Parent  := PageAbout.Surface;
    Caption :=
      'A professional admin tool for managing on-chain withdrawal requests.' + #13#10 + #13#10 +
      'Features:' + #13#10 +
      ' •  View all withdrawal requests with real-time status' + #13#10 +
      ' •  Approve or reject pending withdrawals' + #13#10 +
      ' •  Automatic BH / USDT token transfers on Polygon & BSC' + #13#10 +
      ' •  Multi-network wallet balance viewer (Polygon 137 + BSC 56)' + #13#10 +
      ' •  Double-payment protection - prevents duplicate on-chain sends' + #13#10 +
      ' •  Encrypted private-key storage with passphrase' + #13#10 +
      ' •  Simulation mode for safe testing before going live' + #13#10 + #13#10 +
      'Version 4.0 Updates:' + #13#10 +
      ' •  Improved performance and stability' + #13#10 +
      ' •  Enhanced security features' + #13#10 +
      ' •  Better error handling and logging';
    Font.Size := 9;
    Left      := 0;
    Top       := 62;
    Width     := 440;
    Height    := 220;
    WordWrap  := True;
  end;

  // Social media section
  LblSocialTitle := TLabel.Create(PageAbout);
  with LblSocialTitle do
  begin
    Parent     := PageAbout.Surface;
    Caption    := 'Follow Ayamil Coders:';
    Font.Size  := 9;
    Font.Style := [fsBold];
    Left       := 0;
    Top        := 290;
    Width      := 200;
    Height     := 20;
  end;

  LblFacebook := TLabel.Create(PageAbout);
  with LblFacebook do
  begin
    Parent     := PageAbout.Surface;
    Caption    := ' Facebook: facebook.com/ayamilcoders';
    Font.Color := clBlue;
    Font.Style := [fsUnderline];
    Cursor     := crHand;
    Left       := 0;
    Top        := 314;
    Width      := 300;
    Height     := 20;
    OnClick    := @OnFacebookClick;
  end;

  LblInstagram := TLabel.Create(PageAbout);
  with LblInstagram do
  begin
    Parent     := PageAbout.Surface;
    Caption    := ' Instagram: instagram.com/ayamilcoders';
    Font.Color := $00A01CC5;
    Font.Style := [fsUnderline];
    Cursor     := crHand;
    Left       := 0;
    Top        := 340;
    Width      := 300;
    Height     := 20;
    OnClick    := @OnInstagramClick;
  end;

  // ────────────────────────────────────────────────────────────────
  // PAGE 2 — Wallet Setup (fresh installs only)
  //          OR Update Options (updates only)
  // ────────────────────────────────────────────────────────────────
  if not IsUpdate then
  begin
    PageWallet := CreateCustomPage(
      PageAbout.ID,
      'Wallet Setup',
      'Pre-configure your sending wallet (you can change this inside the app later)'
    );

    LblWalletInfo := TLabel.Create(PageWallet);
    with LblWalletInfo do
    begin
      Parent  := PageWallet.Surface;
      Caption :=
        'Enter the wallet address that will send USDT / BH tokens to customers.' + #13#10 +
        'This wallet must hold:' + #13#10 +
        '  •  MATIC (for gas fees on Polygon), or BNB (for gas on BSC)' + #13#10 +
        '  •  Enough BH or USDT tokens to cover the pending withdrawals';
      Font.Size := 9;
      Left      := 0;
      Top       := 0;
      Width     := 460;
      Height    := 80;
      WordWrap  := True;
    end;

    LblFromAddr := TLabel.Create(PageWallet);
    with LblFromAddr do
    begin
      Parent     := PageWallet.Surface;
      Caption    := 'From Wallet Address:';
      Font.Size  := 9;
      Font.Style := [fsBold];
      Left       := 0;
      Top        := 92;
      Width      := 150;
      Height     := 20;
    end;

    EdtFromAddr := TEdit.Create(PageWallet);
    with EdtFromAddr do
    begin
      Parent    := PageWallet.Surface;
      Text      := '';
      Left      := 0;
      Top       := 116;
      Width     := 460;
      Font.Name := 'Consolas';
      Font.Size := 9;
    end;

    LblPKNote := TLabel.Create(PageWallet);
    with LblPKNote do
    begin
      Parent  := PageWallet.Surface;
      Caption :=
        'WARNING: Your PRIVATE KEY is NOT entered here.' + #13#10 +
        'You will enter it securely inside the app after installation.' + #13#10 +
        'The app encrypts it with a passphrase of your choice and never' + #13#10 +
        'stores it in plain text.' + #13#10 + #13#10 +
        'You can skip this page - the wallet address can also be set' + #13#10 +
        'in Wallet & API Settings after the app opens.';
      Font.Size  := 9;
      Font.Color := $00006614;
      Left       := 0;
      Top        := 154;
      Width      := 460;
      Height     := 140;
      WordWrap   := True;
    end;
  end
  else
  begin
    PageUpdateOptions := CreateCustomPage(
      PageAbout.ID,
      'Update Options',
      'An existing installation of {#AppName} was found on this computer'
    );

    LblUpdateVersions := TLabel.Create(PageUpdateOptions);
    with LblUpdateVersions do
    begin
      Parent     := PageUpdateOptions.Surface;
      Caption    := 'Installed version:   v' + OldVersion + #13#10 +
                     'New version:         v{#AppVersion}';
      Font.Name  := 'Consolas';
      Font.Size  := 10;
      Font.Style := [fsBold];
      Left       := 0;
      Top        := 0;
      Width      := 460;
      Height     := 40;
    end;

    LblWhatsNewTitle := TLabel.Create(PageUpdateOptions);
    with LblWhatsNewTitle do
    begin
      Parent     := PageUpdateOptions.Surface;
      Caption    := 'What''s New in v{#AppVersion}:';
      Font.Size  := 9;
      Font.Style := [fsBold];
      Left       := 0;
      Top        := 46;
      Width      := 200;
      Height     := 20;
    end;

    LblWhatsNew := TLabel.Create(PageUpdateOptions);
    with LblWhatsNew do
    begin
      Parent  := PageUpdateOptions.Surface;
      Caption :=
        ' •  Improved performance and stability' + #13#10 +
        ' •  Enhanced security features' + #13#10 +
        ' •  Better error handling and logging';
      Font.Size := 9;
      Left      := 0;
      Top       := 68;
      Width     := 460;
      Height    := 60;
      WordWrap  := True;
    end;

    LblChooseAction := TLabel.Create(PageUpdateOptions);
    with LblChooseAction do
    begin
      Parent     := PageUpdateOptions.Surface;
      Caption    := 'What would you like to do?';
      Font.Size  := 9;
      Font.Style := [fsBold];
      Left       := 0;
      Top        := 140;
      Width      := 200;
      Height     := 20;
    end;

    RbUpdate := TRadioButton.Create(PageUpdateOptions);
    with RbUpdate do
    begin
      Parent    := PageUpdateOptions.Surface;
      Caption   := 'Update to v{#AppVersion} (recommended) - keep my settings & history';
      Font.Size := 9;
      Left      := 0;
      Top       := 164;
      Width     := 460;
      Height    := 20;
      Checked   := True;
      OnClick   := @OnChooseUpdate;
    end;

    RbRepair := TRadioButton.Create(PageUpdateOptions);
    with RbRepair do
    begin
      Parent    := PageUpdateOptions.Surface;
      Caption   := 'Repair / reinstall v{#AppVersion} - reset wallet & API settings to default';
      Font.Size := 9;
      Left      := 0;
      Top       := 190;
      Width     := 460;
      Height    := 20;
      OnClick   := @OnChooseRepair;
    end;

    RbUninstallFirst := TRadioButton.Create(PageUpdateOptions);
    with RbUninstallFirst do
    begin
      Parent    := PageUpdateOptions.Surface;
      Caption   := 'Uninstall the existing version first, then install v{#AppVersion} fresh';
      Font.Size := 9;
      Left      := 0;
      Top       := 216;
      Width     := 460;
      Height    := 20;
      OnClick   := @OnChooseUninstallFirst;
    end;
  end;
end;

// ── Write initial config after install ─────────────────────────────────
procedure WriteInitialConfig(const FromAddress: string);
var
  ConfigDir:  string;
  ConfigPath: string;
  ConfigJson: string;
begin
  ConfigDir  := ExpandConstant('{userappdata}') + '\.withdrawal_admin';
  ConfigPath := ConfigDir + '\config.json';

  // During updates: DO NOT overwrite existing config
  if IsUpdate then
  begin
    if FileExists(ConfigPath) then
    begin
      Log('Update detected: Keeping existing config file.');
      Exit;
    end;
  end;

  // Only write if the file does not already exist
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
    '  "extra_tokens": []' + #13#10 +
    '}';

  SaveStringToFile(ConfigPath, ConfigJson, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsUpdate then
    begin
      Log('Performing update to version {#AppVersion} (mode=' + IntToStr(UpdateChoice) + ')');

      // Repair or Uninstall-first both reset wallet/API config to default
      if (UpdateChoice = 1) or (UpdateChoice = 2) then
        ResetConfigForRepair();

      // If PageWallet doesn't exist (update), use empty string
      if not Assigned(PageWallet) then
        WriteInitialConfig('')
      else
        WriteInitialConfig(EdtFromAddr.Text);
    end
    else
      WriteInitialConfig(EdtFromAddr.Text);
  end;
end;

// ── Validation / actions on Next ───────────────────────────────────────
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if Assigned(PageWallet) and (not IsUpdate) and (CurPageID = PageWallet.ID) then
  begin
    if (Length(EdtFromAddr.Text) > 0) and (Length(EdtFromAddr.Text) < 42) then
    begin
      MsgBox(
        'Wallet address looks too short. A valid Ethereum/Polygon address' + #13#10 +
        'starts with "0x" and is 42 characters long.' + #13#10 + #13#10 +
        'You can leave it blank and set it in the app later.',
        mbInformation, MB_OK
      );
    end;
  end;

  if Assigned(PageUpdateOptions) and IsUpdate and (CurPageID = PageUpdateOptions.ID) then
  begin
    case UpdateChoice of
      1: begin
           if MsgBox(
                'Repair will reinstall v{#AppVersion} and RESET your wallet & API settings to default.' + #13#10 +
                'Your transaction history and security logs will be kept.' + #13#10 + #13#10 +
                'Continue?', mbConfirmation, MB_YESNO) <> IDYES then
             Result := False;
         end;
      2: begin
           if MsgBox(
                'This will uninstall the currently installed version (v' + OldVersion + ')' + #13#10 +
                'before installing v{#AppVersion}. Your transaction history and security logs' + #13#10 +
                'will be kept, but wallet & API settings will be reset to default.' + #13#10 + #13#10 +
                'Continue?', mbConfirmation, MB_YESNO) = IDYES then
           begin
             if not UninstallPreviousVersion() then
               Result := False;
           end
           else
             Result := False;
         end;
    end;
  end;
end;

// ── Custom Ready Page message ──────────────────────────────────────────
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '';

  if IsUpdate then
  begin
    case UpdateChoice of
      0: begin
           S := S + 'This will update Infinity Meta Hub from v' + OldVersion +
                ' to v{#AppVersion}.' + NewLine;
           S := S + 'Your existing settings, wallet, and history will be preserved.' +
                NewLine + NewLine;
         end;
      1: begin
           S := S + 'This will repair Infinity Meta Hub, reinstalling v{#AppVersion} over v' +
                OldVersion + '.' + NewLine;
           S := S + 'Wallet & API settings will be RESET to default. ' +
                'History and security logs will be kept.' + NewLine + NewLine;
         end;
      2: begin
           S := S + 'The existing v' + OldVersion + ' installation will be removed, ' +
                'then v{#AppVersion} installed fresh.' + NewLine;
           S := S + 'Wallet & API settings will be RESET to default. ' +
                'History and security logs will be kept.' + NewLine + NewLine;
         end;
    end;
  end;

  if MemoDirInfo <> '' then
    S := S + MemoDirInfo + NewLine + NewLine;

  if MemoGroupInfo <> '' then
    S := S + MemoGroupInfo + NewLine + NewLine;

  if MemoTasksInfo <> '' then
    S := S + MemoTasksInfo + NewLine + NewLine;

  Result := S;
end;

// ── Skip pages during upgrade ──────────────────────────────────────────
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;

  // Skip wallet setup page during updates (Update Options page replaces it)
  if Assigned(PageWallet) and IsUpdate and (PageID = PageWallet.ID) then
    Result := True;
end;
