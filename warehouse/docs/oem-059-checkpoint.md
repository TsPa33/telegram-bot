# CarPot OEM №059 — контрольна точка

- Issue [#557](https://github.com/TsPa33/telegram-bot/issues/557). Warehouse staging базується на `c2390aa36a14e38a41cbbbe350f5465a66c17201`. Catalogue staging базується на `d10f659e5b603780e87e6df799ae5821a9e18fea`.
- Warehouse перевірено на ізольованому PostgreSQL. VIN із підтвердженою модифікацією → автоматичний план за стабільним ID → OEM з походженням і часом отримання → складська картка. Повторний прогін не дублює план і не змінює наявні ручні позиції. Окремі тести покривають дозаповнення, ручний вибір, перевірку сторони та ізоляцію workspace.
- Catalogue повертає вже імпортовані OEM за ключем постачальник + артикул + виробник автомобіля тільки після перевірки зв'язку типу й артикула у запитаному знімку модифікації. Той самий SHA і граф збережено. [Catalogue PR #558](https://github.com/TsPa33/telegram-bot/pull/558)
- Вихідні показники з issue #557. XC90 `YV4A22PK2G1092943` має 16 валідних OEM на 196 позицій (8,16%) і 0 складських деталей. XC60 `YV4L12RK6N1970668` має 0 позицій і невизначену модифікацію. DAF XF `XLRTE47MS0E774889` має 0 OEM на 227 пов'язаних складських позицій (0%).
- З Codex Cloud з'єднання з `127.0.0.1:3306` відхилено. Оригінал `td1q2018` та staging MySQL не змінювалися. Зіставлення живих джерел, імпорт, післярелізні показники, покриття DAF та підтверджене застосування на інших моделях залишаються відкритими.

## Експорт із машини з td1q2018

Запустіть PowerShell у корені checkout репозиторію з Python і MySQL CLI. Використайте обліковий запис із правом SELECT до `td1q2018`. Команди зберігають результати лише у файлову систему Windows. Дозволи MySQL не змінюються.

```powershell
$auditDir = Join-Path $env:TEMP 'carpot-oem059-audit'
New-Item -ItemType Directory -Force $auditDir | Out-Null
$source = Get-Credential -Message 'Локальна MySQL td1q2018 — обліковий запис для читання'
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user="$($source.UserName)" --password --batch --execute "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='td1q2018' AND (TABLE_NAME IN ('article_links','article_oe','articles','manufacturers','models','prd') OR TABLE_NAME LIKE '%car%' OR TABLE_NAME LIKE '%commercial%' OR TABLE_NAME LIKE '%truck%') ORDER BY TABLE_NAME;" | Set-Content -Encoding utf8 (Join-Path $auditDir 'source-tables.tsv')
if ($LASTEXITCODE -ne 0) { throw 'Не вдалося виконати аудит MySQL.' }

$cataloguePython = Join-Path $auditDir 'venv\Scripts\python.exe'
py -3 -m venv (Join-Path $auditDir 'venv')
& $cataloguePython -m pip install 'PyMySQL==1.1.1'
$env:SOURCE_HOST = '127.0.0.1'
$env:SOURCE_PORT = '3306'
$env:SOURCE_DATABASE = 'td1q2018'
$env:SOURCE_USER = $source.UserName
$env:SOURCE_PASSWORD = $source.GetNetworkCredential().Password
try {
    & $cataloguePython catalogue/vehicle_source_batch.py export --car-id 107555 --discover-model XC60 --max-modifications 4 --graph-only --output (Join-Path $auditDir 'volvo-graph')
    if ($LASTEXITCODE -ne 0) { throw 'Експорт не завершився. Для продовження залиште ті самі аргументи й каталог.' }
} finally {
    Remove-Item Env:SOURCE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Variable source
}
```

Передайте `source-tables.tsv`, каталог `volvo-graph` і SHA маніфесту. Команда відкриває транзакцію READ ONLY і відновлює експорт із перевіреного checkpoint. Результати пошуку XC60 є кандидатами. Для імпорту потрібні звірка з підтвердженими характеристиками VIN, порівняння зі staging inventory і перевірка класифікації PRD. Графовий експорт містить зв'язки застосовності. OEM і атрибути встановлення окремо звіряються з уже завантаженими даними або підтвердженим повним експортом тільки для відсутніх артикулів.
