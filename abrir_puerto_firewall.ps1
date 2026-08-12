# abrir_puerto_firewall.ps1
# Corre esto UNA VEZ en la PC donde vive el servidor SGIJ, como Administrador
# (click derecho sobre PowerShell -> "Ejecutar como administrador"), antes
# de dejar el sistema en uso en la tienda del cliente.
#
# Abre el puerto 5000 (el que usa `python app.py`) para conexiones
# entrantes desde la red local, para que el celular con la app movil
# pueda alcanzar al servidor. Sin esto, el Firewall de Windows puede
# bloquear la conexion en silencio aunque el servidor este corriendo bien.

$reglaExistente = Get-NetFirewallRule -DisplayName "SGIJ - Servidor Jugueteria (5000)" -ErrorAction SilentlyContinue

if ($reglaExistente) {
    Write-Host "La regla de firewall ya existe, no se crea de nuevo." -ForegroundColor Yellow
} else {
    New-NetFirewallRule -DisplayName "SGIJ - Servidor Jugueteria (5000)" `
        -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow -Profile Any
    Write-Host "Regla de firewall creada: puerto 5000 TCP abierto para conexiones entrantes." -ForegroundColor Green
}

Write-Host ""
Write-Host "IP local de esta PC (usar esta IP en la app movil, en Configuracion):" -ForegroundColor Cyan
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback|vEthernet" } | Select-Object InterfaceAlias, IPAddress
