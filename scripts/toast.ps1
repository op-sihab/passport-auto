param(
  [string]$Title = "Passport Auto",
  [string]$Msg = "",
  [string]$Logo = ""
)
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)

if ($Logo -and (Test-Path $Logo)) {
  $uri = "file:///" + ($Logo -replace '\\','/')
  $img = $tpl.CreateElement('image')
  $img.SetAttribute('placement','appLogoOverride')
  $img.SetAttribute('hint-crop','circle')
  $img.SetAttribute('src', $uri)
  $tpl.DocumentElement.AppendChild($img) | Out-Null
}

$texts = $tpl.GetElementsByTagName('text')
$texts.Item(0).AppendChild($tpl.CreateTextNode($Title)) | Out-Null
$texts.Item(1).AppendChild($tpl.CreateTextNode($Msg)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:PA_TOAST_APPID).Show($toast)
