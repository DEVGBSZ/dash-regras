@echo off
title Autenticacao do SharePoint - Dashboard CCEE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0autenticar_sharepoint.ps1"
if errorlevel 1 (
  echo.
  echo Nao foi possivel concluir a autenticacao.
  pause
)
