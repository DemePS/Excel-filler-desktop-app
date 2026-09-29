# Signing ExcelFiller.exe (Azure Trusted Signing)

The Windows build (`azure-pipelines.yml`) signs `ExcelFiller.exe` when it runs with the parameter
**sign** set to true; otherwise builds are unsigned and releases are refused (unless
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
4. **A service connection for the pipeline** (no secret stored): in the Azure DevOps project,
   *Project settings > Service connections > New > Azure Resource Manager*, **Workload identity
   federation**, scoped to the signing account's subscription or resource group, named
   `excel-filler-signing`. Allow the Excel filler pipeline to use it.
5. **Permission to sign.** On the certificate profile: *Access control (IAM)* > add the role
   **Trusted Signing Certificate Profile Signer** to the service connection's identity (its app
   registration is shown in the service connection's details).
6. **Variables** (Pipelines > Library > variable group `excel-filler`):

   | Variable | Value |
   |---|---|
   | `SIGNING_ENDPOINT` | the account's endpoint, e.g. `https://weu.codesigning.azure.net/` |
   | `SIGNING_ACCOUNT` | the Trusted Signing account name |
   | `SIGNING_PROFILE` | the certificate profile name |

7. Run the pipeline with **sign** set to true (or change the parameter's default in
   `azure-pipelines.yml` to `true` so that every build is signed).

## Checking a signature

The pipeline prints it ("Signature: Valid CN=..."). On a PC: right-click `ExcelFiller.exe` >
Properties > *Digital Signatures*, or in PowerShell:

```powershell
Get-AuthenticodeSignature .\ExcelFiller\ExcelFiller.exe | Format-List Status, SignerCertificate
```
