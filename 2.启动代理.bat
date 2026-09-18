@echo off


cd /d "%~dp0"

title hainnu 代理



rem ============================================================

rem  启动本地代理

rem

rem  重要：这里**不再无脑杀端口**。

rem  桥是单线程的，处理长请求时连 /health 都不回，但端口照样在监听。

rem  老版本「netstat 找到 8787 就 taskkill」会因此杀掉一个只是"忙"的

rem  健康桥，客户端立刻 connection refused —— 这就是"桥老是掉"的主因之一。

rem  现在交给 _port_guard.py 判断：

rem    端口没人听        -> 正常启动

rem    有桥且健康        -> 什么都不做（想换新实例请用管理台的「重启代理」）

rem    有人在听但不健康  -> 视为"忙"，默认不动；确认是残留才用 force 强制启动

rem ============================================================



call _find_python.bat

if errorlevel 1 (

  pause

  exit /b 1

)



set "FORCE="

if /i "%~1"=="force" set "FORCE=--force"



echo.

echo   ============================================================

echo     启动本地代理（不会误杀正在运行的桥）

echo   ============================================================

"%PY%" "%~dp0_port_guard.py" check %FORCE%

set "RC=%ERRORLEVEL%"



if "%RC%"=="10" (

  echo.

  echo   已有健康代理在运行，本次未做任何改动。

  echo.

  pause

  exit /b 0

)



if "%RC%"=="11" (

  echo.

  echo   确认那只是残留进程、要强制换新实例，请这样启动：

  echo       2.启动代理.bat force

  echo.

  pause

  exit /b 0

)



rem ---- 到这里 RC=0：端口上确实没人，或已按 force 授权 ----

"%PY%" "%~dp0_port_guard.py" free



echo.

echo  Proxy starting on http://127.0.0.1:8787/v1

echo  OpenAI    : http://127.0.0.1:8787/v1/chat/completions

echo  Anthropic : http://127.0.0.1:8787/v1/messages

echo  Health    : http://127.0.0.1:8787/health?probe=1

echo.

echo  关掉本窗口 = 停止代理。

echo.



"%PY%" hainnu_proxy.py

pause

