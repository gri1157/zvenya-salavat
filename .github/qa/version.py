"""Проверка версии: в PR APP_VERSION должна быть больше, чем в main.
Запуск: python3 .github/qa/version.py <index.html из main> <index.html из PR>"""
import re, sys


def ver(path):
    m = re.search(r'const APP_VERSION="(\d+)\.(\d+)"', open(path, encoding='utf-8').read())
    if not m:
        if 'base' in path:
            return 0, 0  # в main ещё нет версии — первое включение
        sys.exit('не найдена константа APP_VERSION в ' + path)
    return int(m.group(1)), int(m.group(2))


old, new = ver(sys.argv[1]), ver(sys.argv[2])
print('версия в main: %d.%d, в PR: %d.%d' % (old + new))
if new <= old:
    sys.exit('ОШИБКА: поднимите APP_VERSION (и допишите CHANGELOG.md): каждое слияние — новая версия')
print('версия повышена')
