# ASCII source intentionally supports Windows PowerShell 5.1 without encoding issues.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+$')][string]$Target,
    [Parameter(Mandatory=$true)][string]$Key,
    [switch]$Resume
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Key -PathType Leaf)) { throw 'SSH key not found.' }
$sshArgs = @('-T','-i',$Key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=10',$Target)
# This helper requires an existing key and passwordless sudo; it grants neither.
& ssh @sshArgs 'sudo -n test -x /usr/local/sbin/thinksmart-muse-pair'
if ($LASTEXITCODE -ne 0) { throw 'SSH/sudo preflight failed. Do not paste a token. Use the normal SSH pairing instructions.' }
if ($Resume) {
    & ssh @sshArgs 'sudo -n /usr/local/sbin/thinksmart-muse-pair --resume'
} else {
    $secure = Read-Host 'Paste Muse SDK Token (hidden)' -AsSecureString
    $ptr = [IntPtr]::Zero
    try {
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        if ($plain -notmatch '^mgst_[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$') { throw 'Invalid token format; nothing saved.' }
        $plain | & ssh @sshArgs 'sudo -n /usr/local/sbin/thinksmart-muse-pair --stdin'
    } finally {
        $plain = $null
        if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        if ($secure) { $secure.Dispose() }
    }
}
if ($LASTEXITCODE -ne 0) { throw 'Pairing did not finish. Copy only the error, never the token.' }
