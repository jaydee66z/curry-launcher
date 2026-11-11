@echo off
REM Shutdown the machine in 3 hours (10800 seconds).
REM Run this .bat when you want to start the countdown. Cancel with
REM   shutdown /a
REM Produced by C.C. during the overnight sprint.
shutdown /s /t 10800 /c "Programado tras sesion de port Luau->Python"
echo Shutdown programado en 10800s (3h). Cancelar con: shutdown /a
pause
