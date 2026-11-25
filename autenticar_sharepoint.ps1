$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Autenticação do SharePoint - Dashboard CCEE"

Write-Host "Autenticação do SharePoint" -ForegroundColor Cyan
Write-Host "Será aberta uma autenticação Microsoft da CCEE com acesso somente de leitura aos arquivos."
Write-Host "Siga as instruções exibidas e entre com a mesma conta que abre a planilha.`n"

Import-Module Microsoft.Graph.Authentication
$connection = @{
    Scopes = "Files.Read"
    UseDeviceCode = $true
    ContextScope = "CurrentUser"
    NoWelcome = $true
}
if ($env:MICROSOFT_CLIENT_ID -and $env:MICROSOFT_TENANT_ID) {
    $connection.ClientId = $env:MICROSOFT_CLIENT_ID
    $connection.TenantId = $env:MICROSOFT_TENANT_ID
}

try {
    Connect-MgGraph @connection
} catch {
    Write-Host "`nA CCEE bloqueou o aplicativo Microsoft usado para autenticação." -ForegroundColor Red
    Write-Host "Solicite ao administrador acesso ao aplicativo corporativo ou configure uma aplicação própria."
    throw
}

$context = Get-MgContext
if ($null -eq $context) {
    throw "A autenticação não foi concluída."
}

Write-Host "`nAutenticação concluída para $($context.Account)." -ForegroundColor Green
Write-Host "Volte ao dashboard e clique em Atualizar dados."
Read-Host "Pressione Enter para fechar"
