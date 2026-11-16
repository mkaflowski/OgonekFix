#!/bin/sh
# Polskie znaki w fontach gry (Unity / Unreal) - uruchamia fix_game_fonts.py.
#   sh napraw_fonty.sh ["/sciezka/do/gry"] [--auto ...]
# POSIX sh, bez bashizmow. Narzedzie Unreala wymaga repak w PATH.

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONUTF8=1
export PYTHONUTF8

PY=
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY=$cand
        break
    fi
done

if [ -z "$PY" ]; then
    echo
    echo "Nie znaleziono Pythona (python3 / python). Zainstaluj Python 3.10+."
    RC=9
else
    "$PY" "$DIR/fix_game_fonts.py" "$@"
    RC=$?
    echo
    case $RC in
        0) echo "Zakonczono: fonty naprawione." ;;
        1) echo "Zakonczono z ostrzezeniami: czesc fontow sie nie udala (kod 1)." ;;
        2) echo "Zakonczono: nie bylo czego naprawiac (kod 2)." ;;
        3) echo "Nie rozpoznano silnika gry albo katalogu (kod 3)." ;;
        *) echo "Narzedzie zakonczylo sie bledem (kod $RC) - tresc bledu jest powyzej." ;;
    esac
fi

# okno terminala otwarte dwuklikiem nie moze zniknac razem z komunikatem
if [ -t 0 ]; then
    printf '\nNacisnij Enter, aby zamknac... '
    read -r _ || true
fi
exit "$RC"
