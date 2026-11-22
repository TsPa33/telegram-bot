# CarPot: Oracle OEM / PRD — етап 1

Пробник читає тільки метадані завершених таблиць Oracle MySQL та, за окремим параметром, до 20 рядків індексованої вибірки. Під час імпорту article_li немає повних сканувань, COUNT(*), DDL або змін даних. Незавершені article_li та article_links не опитуються.

## Windows PowerShell

Відкрийте чинний SSH-тунель **до Oracle**, не до Railway MySQL. Використовуйте MySQL-користувача лише з правами SELECT. Реальний локальний порт тунелю, ім'я користувача та пароль мають залишатися локально.

~~~powershell
$env:ORACLE_MYSQL_HOST = "127.0.0.1"
$env:ORACLE_MYSQL_PORT = "<порт SSH-тунелю>"
$env:ORACLE_MYSQL_DATABASE = "td1q2018"
$env:ORACLE_MYSQL_USER = "<read-only користувач>"
$env:ORACLE_MYSQL_PASSWORD = "<пароль>"
py -3 -m pip install "PyMySQL==1.1.1"
py -3 .\catalogue\oracle_oem_readonly_probe.py --mode preflight --output "C:\CarPot\exports\oracle-oem-readonly"
~~~

Перевірте в JSON поле capabilities. Якщо car_prd_lookup=true, дозволена лише точкова перевірка (car_id із раніше верифікованого каталогу):

~~~powershell
py -3 .\catalogue\oracle_oem_readonly_probe.py --mode prd --car-id 107555 --output "C:\CarPot\exports\oracle-oem-readonly"
~~~

OEM за точно відомою парою постачальник+артикул та manufacturer_id:

~~~powershell
py -3 .\catalogue\oracle_oem_readonly_probe.py --mode oem --supplier-id <ID> --article-number "<АРТИКУЛ>" --maker-id <ID> --output "C:\CarPot\exports\oracle-oem-readonly"
~~~

Не запускайте приклад OEM до встановлення реальних ID і номера. Якщо індексу немає, запит не виконується. EXPLAIN відхиляє full scan або план понад 20 тисяч оцінених рядків. Використовувати створений звіт для наступного етапу: Oracle Catalogue Adapter. Цей скрипт не змінює Railway, Warehouse, налаштування Oracle, production і не доводить VIN-сумісність.

Тести: py -3 -m pytest -q catalogue/tests/test_oracle_oem_readonly_probe.py
