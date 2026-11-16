@echo off
rem Polskie znaki w fontach gry (Unity / Unreal) - uruchamia fix_game_fonts.py.
rem Dwuklik albo: napraw_fonty.bat "E:\Gry\Gra" [--auto ...]
rem Plik celowo bez polskich znakow (cmd startuje w cp852).
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"

set PY=
where py >nul 2>nul
if not errorlevel 1 set PY=py -3
if defined PY goto run
where python >nul 2>nul
if not errorlevel 1 set PY=python
if defined PY goto run
where python3 >nul 2>nul
if not errorlevel 1 set PY=python3
if defined PY goto run

echo.
echo Nie znaleziono Pythona (py / python / python3).
echo Zainstaluj Python 3.10+ z https://www.python.org/downloads/
set RC=9
goto end

:run
%PY% "%~dp0fix_game_fonts.py" %*
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" echo Zakonczono: fonty naprawione.
if "%RC%"=="1" echo Zakonczono z ostrzezeniami: czesc fontow sie nie udala ^(kod 1^).
if "%RC%"=="2" echo Zakonczono: nie bylo czego naprawiac ^(kod 2^).
if "%RC%"=="3" echo Nie rozpoznano silnika gry albo katalogu ^(kod 3^).
if %RC% GTR 3 echo Narzedzie zakonczylo sie bledem ^(kod %RC%^) - tresc bledu jest powyzej.

:end
popd
echo.
pause
endlocal & exit /b %RC%
