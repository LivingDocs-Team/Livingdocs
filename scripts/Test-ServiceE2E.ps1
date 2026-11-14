<#
.SYNOPSIS
    Kich ban kiem thu hoi quy E2E cho Windows Services (Fixed Syntax & Encoding)
#>

param (
    [string[]]$ServiceNames = @("Spooler", "W3SVC"),
    [hashtable]$EndpointMap = @{
        "W3SVC" = "http://localhost:80/health"
    },
    [int]$TimeoutSeconds = 30,
    [string]$LogPath = "C:\TestLogs\E2E_Service_Regression.log"
)

# Tao thu muc log neu chua co
$logDir = Split-Path $LogPath
if ($logDir -and (-not (Test-Path $logDir))) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-TestLog {
    param (
        [string]$Message,
        [string]$Type = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Type] $Message"
    
    $color = switch ($Type) {
        "ERROR"   { "Red" }
        "SUCCESS" { "Green" }
        default   { "Cyan" }
    }
    
    Write-Host $logEntry -ForegroundColor $color
    Add-Content -Path $LogPath -Value $logEntry -Encoding UTF8
}

Write-TestLog "================= BAT DAU KIEM THU HOI QUY E2E ================="

$testResults = @()

foreach ($serviceName in $ServiceNames) {
    Write-TestLog "--- Checking Service: $serviceName ---"
    
    # 1. PRE-CHECK: Kiem tra su ton tai
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-TestLog "Dich vu '$serviceName' khong ton tai tren he thong!" "ERROR"
        $testResults += [PSCustomObject]@{
            ServiceName = $serviceName
            Step        = "Pre-Check"
            Status      = "FAILED"
            Details     = "Service not found"
        }
        continue
    }

    # 2. ACTION: Restart Service
    try {
        Write-TestLog "Dang gui lenh Restart-Service cho '$serviceName'..."
        Restart-Service -Name $serviceName -Force -ErrorAction Stop
        Write-TestLog "Lenh Restart da gui thanh cong." "SUCCESS"
    }
    catch {
        $errMessage = $_.Exception.Message
        Write-TestLog "Khong the restart dich vu '$serviceName': $errMessage" "ERROR"
        $testResults += [PSCustomObject]@{
            ServiceName = $serviceName
            Step        = "Restart Action"
            Status      = "FAILED"
            Details     = $errMessage
        }
        continue
    }

    # 3. VERIFICATION STEP 1: Trang thai Process (Running)
    $elapsed = 0
    $isStatusOk = $false
    while ($elapsed -lt $TimeoutSeconds) {
        $service.Refresh()
        if ($service.Status -eq 'Running') {
            $isStatusOk = $true
            break
        }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }

    if (-not $isStatusOk) {
        Write-TestLog "Timeout ($($TimeoutSeconds)s): Dich vu '$serviceName' khong chuyen sang Running." "ERROR"
        $testResults += [PSCustomObject]@{
            ServiceName = $serviceName
            Step        = "Status Verification"
            Status      = "FAILED"
            Details     = "Timeout waiting for Running state"
        }
        continue
    }

    # 4. VERIFICATION STEP 2: Endpoint / App Health Check
    $isAppOk = $true
    $appDetails = "Service Running successfully"

    if ($EndpointMap.ContainsKey($serviceName)) {
        $url = $EndpointMap[$serviceName]
        Write-TestLog "Dang kiem tra Healthcheck Endpoint: $url"
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-TestLog "Endpoint $url phan hoi HTTP 200 OK." "SUCCESS"
                $appDetails += " | HTTP 200 OK"
            } else {
                $isAppOk = $false
                $appDetails = "Endpoint returned Status Code: $($response.StatusCode)"
            }
        }
        catch {
            $isAppOk = $false
            $errMessage = $_.Exception.Message
            $appDetails = "Endpoint Check Failed: $errMessage"
            Write-TestLog $appDetails "ERROR"
        }
    }

    # Tong hop ket qua cho dich vu
    $finalStatus = if ($isAppOk) { "PASSED" } else { "FAILED" }
    $testResults += [PSCustomObject]@{
        ServiceName = $serviceName
        Step        = "E2E Complete Check"
        Status      = $finalStatus
        Details     = $appDetails
    }
}

# 5. REPORTING & EXIT CODE
Write-TestLog "================= TONG HOP KET QUA ================="
$testResults | Format-Table -AutoSize

$csvReport = $LogPath.Replace(".log", "_Summary.csv")
$testResults | Export-Csv -Path $csvReport -NoTypeInformation -Encoding UTF8
Write-TestLog "Bao cao chi tiet da duoc xuat ra file: $csvReport" "SUCCESS"

# 6. KIEM TRA KET QUA & GUI CANH BAO WEBHOOK
if ($testResults.Status -contains "FAILED") {
    Write-TestLog "Ket qua kiem thu: FAILED - Co dich vu gap loi!" "ERROR"
    
    # URL Webhook (Thay đường dẫn Incoming Webhook thực tế của Teams/Slack vào đây)
    $webhookUrl = "https://your-teams-or-slack-webhook-url"
    
    # Chỉ tự động gửi Webhook nếu bạn đã thay đổi URL mẫu
    if ($webhookUrl -and ($webhookUrl -ne "https://your-teams-or-slack-webhook-url")) {
        try {
            $failedServices = ($testResults | Where-Object Status -eq "FAILED").ServiceName -join ", "
            $payload = @{
                text = "CANH BAO E2E TEST FAIL: Cac dich vu sau gap su co: $failedServices"
            } | ConvertTo-Json

            Invoke-RestMethod -Uri $webhookUrl -Method Post -Body $payload -ContentType 'application/json' -TimeoutSec 10
            Write-TestLog "Da gui canh bao qua Webhook thanh cong." "SUCCESS"
        }
        catch {
            Write-TestLog "Khong the gui Webhook canh bao: $($_.Exception.Message)" "ERROR"
        }
    }

    exit 1  # Báo cho CI/CD dừng tiến trình (Build Failed)
} else {
    Write-TestLog "Ket qua kiem thu: PASSED - Tat ca dich vu hoat dong tot." "SUCCESS"
    exit 0  # Báo cho CI/CD tiến trình thành công
}


