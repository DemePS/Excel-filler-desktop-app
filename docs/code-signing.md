# Signing ExcelFiller.exe (Azure Trusted Signing)

The Windows build (`.github/workflows/windows-app.yml`) signs `ExcelFiller.exe` when the signing
variables below are set; otherwise builds are unsigned and releases are refused (unless
`ALLOW_UNSIGNED_RELEASE` is `true`). A signed, timestamped app does not show "Windows protected your
PC" (SmartScreen) once the publisher has a reputation, and company policies can trust its publisher.
Apps deployed through Intune do not get the SmartScreen prompt, signed or not.

## One-time setup (Azure administrator)

1. **Trusted Signing account.** Azure portal > create a *Trusted Signing account* (resource provider
   `Microsoft.CodeSigning`) in your subscription and region.
2. **Identity validation.** In the account: *Identity validations* > new, *Public* (your
   organization's legal identity; Microsoft verifies it, which can take several days). Check the
   current eligibility conditions and price in the portal.
3. **Certificate profile.** In the account: *Certificate profiles* > new, type *Public Trust*, using
   that identity validation.
4. **An identity for the workflow** (no secret stored in GitHub):
   ```powershell
   $app = az ad app create --display-name "Excel filler code signing" | ConvertFrom-Json
   az ad sp create --id $app.appId
   # Trust this repository's workflow runs (federated credential):
   '{"name":"excel-filler-github","issuer":"https://token.actions.githubusercontent.com",
     "subject":"repo:DemePS/Excel-filler-desktop-app:ref:refs/tags/*","audiences":["api://AzureADTokenExchange"]}' |
     Set-Content fc.json
   az ad app federated-credential create --id $app.appId --parameters fc.json
   ```
   The subject above allows signing for tag builds (releases). To also sign branch builds, add a
   credential with the subject `repo:DemePS/Excel-filler-desktop-app:ref:refs/heads/api-management`.
5. **Permission to sign.** On the certificate profile: *Access control (IAM)* > add the role
   **Trusted Signing Certificate Profile Signer** to "Excel filler code signing".
6. **Repository variables** (GitHub > Settings > Secrets and variables > Actions > Variables):

   | Variable | Value |
   |---|---|
   | `SIGNING_ENDPOINT` | the account's endpoint, e.g. `https://weu.codesigning.azure.net/` |
   | `SIGNING_ACCOUNT` | the Trusted Signing account name |
   | `SIGNING_PROFILE` | the certificate profile name |
   | `SIGNING_CLIENT_ID` | the application (client) ID of "Excel filler code signing" |
   | `SIGNING_TENANT_ID` | your tenant ID |
   | `SIGNING_SUBSCRIPTION_ID` | the subscription of the signing account |

## Checking a signature

The workflow prints it ("Signature: Valid CN=..."). On a PC: right-click `ExcelFiller.exe` >
Properties > *Digital Signatures*, or in PowerShell:

```powershell
Get-AuthenticodeSignature .\ExcelFiller\ExcelFiller.exe | Format-List Status, SignerCertificate
```
