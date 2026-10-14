# 🛰️ meteor — архивирование спутниковых снимков «Метеор-М»

![GitHub repo size](https://img.shields.io/github/repo-size/VladBus/meteor?label=repo%20size)
![GitHub License](https://img.shields.io/github/license/VladBus/meteor)
![GitHub top language](https://img.shields.io/github/languages/top/VladBus/meteor)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![OS](https://img.shields.io/badge/OS-Windows%2010-0078D6?logo=windows&logoColor=white)
![FTP](https://img.shields.io/badge/source-FTP-informational)

> **RU:** Автоматическая загрузка снимков БРЛК «Метеор-М» с FTP, сортировка по дате съёмки и аудит сетевого TIFF-архива.
>
> **EN:** Automated FTP retrieval of Meteor-M satellite images, acquisition-date sorting, and validation of a network TIFF archive.

---

<a id="russian"></a>

## 🇷🇺 Русский

## ✅ Назначение проекта

`meteor` выполняет один цикл обработки и завершает работу. Ежедневный запуск выполняется через Планировщик заданий Windows (`taskschd.msc`).

| Этап | Что делает программа |
|---|---|
| 🗂️ Сортировка | Находит подходящие TIFF в существующем архиве и переносит их в недельные каталоги по дате из имени файла. |
| 🌐 FTP | Проверяет файлы в заданном удалённом каталоге и скачивает отсутствующие или имеющие известное расхождение размера. |
| 🛡️ Проверка загрузки | Сначала сохраняет файл как `.part`; публикует его в архиве после завершения передачи и проверки размера, когда FTP сообщает размер. |
| 🔎 Аудит | Проверяет расположение снимков, распознавание даты и наличие временных или посторонних файлов. |
| 🧹 Очистка | Удаляет только пустые каталоги старой структуры. Файлы на диске и на FTP автоматически не удаляются. |

**Обработка изображений не выполняется:** GDAL, сжатие TIFF и отправка электронной почты проекту не требуются.

## 🗓️ Структура архива

Корневой каталог по умолчанию — `Z:\ENVISAT\METEOP`. Каждый период начинается **во вторник** и заканчивается в следующий понедельник включительно. Так снимки, приходящие в понедельник как продолжение пролёта, остаются в одном каталоге с предыдущими днями.

Номер `Wnn` — номер ISO-недели для даты начала периода (вторника). Родительская папка года определяется по ISO-году этой даты.

Пример для октября 2026 года:

```text
Z:\ENVISAT\METEOP\
└── 2026\
    ├── W40_2026-09-29_2026-10-05\
    └── W41_2026-10-06_2026-10-12\
```

Например, снимок `METM24_20261012t003301_13586_1_1_BRLK_RLI_log10.tif` будет помещён в:

```text
2026\W41_2026-10-06_2026-10-12\
```

Периоды не разрезаются по границе месяца. Вблизи Нового года год каталога может отличаться от календарного года даты съёмки: он вычисляется по ISO-году даты начала периода.

## 🔍 Правила обработки и безопасности

| Ситуация | Поведение |
|---|---|
| Файл уже находится в целевом каталоге | Повторно не перемещается. |
| Целевой файл с таким именем уже есть при сортировке | Исходный и целевой файлы сохраняются; конфликт отражается в журнале, а аудит укажет на файл не на своём месте. |
| Файл уже есть и его размер совпадает с размером FTP | Повторная загрузка пропускается. |
| FTP сообщает размер, а локальный файл имеет другой размер | Файл загружается во временный `.part` и заменяет целевой только после успешной передачи и проверки размера. |
| FTP не позволяет получить размер существующего файла | Существующий локальный файл не перезаписывается. |
| Обнаружен файл `.part` или посторонний файл | Файл отмечается аудитом, но автоматически не удаляется. |
| Встречается `Thumbs.db` | Служебный кэш миниатюр Windows игнорируется. |
| После сортировки остались пустые каталоги | Удаляются только пустые каталоги. |

Скрипт не удаляет исходные снимки с FTP. Если аудит находит проблемы, программа возвращает ненулевой код завершения, чтобы запуск можно было заметить в Планировщике.

## 🧰 Используемые технологии

| Компонент | Назначение | Версия / требование |
|---|---|---|
| Python | Логика обработки, сортировка и FTP-клиент | Python 3.10+; проверено локально на 3.14.3 |
| `python-dotenv` | Чтение локальных настроек из `.env` | `>=1.0,<2.0` |
| `unittest` | Проверки локальной логики без FTP и сетевого архива | Входит в стандартную библиотеку Python |
| Windows Task Scheduler | Ежедневный запуск | `taskschd.msc` |
| FTP | Источник снимков | По умолчанию `ftp.ntsomz.ru:21` |

## 🚀 Установка

Откройте CMD и перейдите в каталог проекта. Если виртуальное окружение ещё не создано, создайте его:

```bat
cd /d E:\Programming_Work\VScode_Work\meteor
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Отредактируйте локальный файл `.env` и заполните учётные данные FTP. Если окружение `.venv` уже создано, повторно создавать его не требуется.

🔐 **Не помещайте пароль в `main.py`, `run_meteor.bat`, README или другие отслеживаемые Git-файлы.** Настоящий `.env` исключён из Git.

## ⚙️ Настройки `.env`

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `METEOR_FTP_HOST` | `ftp.ntsomz.ru` | FTP-сервер |
| `METEOR_FTP_PORT` | `21` | Порт FTP |
| `METEOR_FTP_USER` | Не задано | Имя пользователя FTP — обязательно заполнить |
| `METEOR_FTP_PASSWORD` | Не задано | Пароль FTP — обязательно заполнить |
| `METEOR_FTP_REMOTE_DIR` | `.` | Удалённый каталог после авторизации; точка означает текущий каталог |
| `METEOR_FTP_TIMEOUT` | `60` | Тайм-аут сетевых операций, секунды |
| `METEOR_DEST_DIR` | `Z:\ENVISAT\METEOP` | Корневой каталог сетевого архива |
| `METEOR_FILE_GLOB` | `METM24_*_BRLK_RLI_log10.tif` | Маска имён снимков |
| `METEOR_LOG_DIR` | `logs` | Каталог журналов; относительный путь считается от каталога проекта |

Маска по умолчанию предназначена для снимков БРЛК «Метеор-М». Распознаются расширения `.tif` и `.tiff`.

## ▶️ Запуск и тестирование

**Запуск тестов** — не подключается к FTP и не меняет рабочий сетевой архив:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

В репозитории есть тесты разбора даты, границ периодов вторник–понедельник, переходов между месяцами и годами, обработки `.tif/.tiff`, сортировки, конфликтов и аудита. При последней локальной проверке прошли все **13 тестов**.

**Полный цикл обработки** можно запустить вручную:

```bat
.venv\Scripts\python.exe main.py
```

или через пакетный файл:

```bat
run_meteor.bat
```

Для повседневной работы предпочтителен запуск через `run_meteor.bat`: он использует интерпретатор из `.venv`, записывает сведения о старте и завершении и возвращает код завершения Python.

## 🕒 Планировщик заданий Windows

Проверенная конфигурация ежедневного задания:

| Параметр | Значение |
|---|---|
| Триггер | Ежедневно в **10:30** |
| Действие — программа | `C:\Windows\System32\cmd.exe` |
| Аргументы | `/d /c ""<ПУТЬ_К_ПРОЕКТУ>\run_meteor.bat""` |
| Рабочая папка | Каталог проекта, без кавычек |
| Учётная запись | Пользователь Windows, у которого есть доступ к FTP и архиву |
| Режим | Выполнять только для вошедшего в систему пользователя |
| Если задача уже выполняется | Не запускать новый экземпляр |
| Пропущенный запуск | Запустить при первой возможности |

Замените `<ПУТЬ_К_ПРОЕКТУ>` на реальный путь на своём компьютере. Для текущей установки это `E:\Programming_Work\VScode_Work\meteor`.

✅ Задача работает независимо от VS Code: во время запуска можно пользоваться другими программами и работать с компьютером. Открывать проект вручную не нужно.

⚠️ Диск `Z:` — сопоставленный сетевой диск. Поэтому задание настроено на запуск в пользовательском сеансе Windows, где этот диск доступен. Для работы после выхода пользователя надёжнее настроить UNC-путь к сетевому ресурсу и проверить права доступа; одного переключения на режим фонового запуска недостаточно.

В каталоге проекта после пробного запуска проверьте журналы. В Планировщике успешное завершение обычно отображается как `0x0`.

### 🖼️ Пример

| Иллюстрация | Файл в репозитории |
|---|---|
| Пример настройки / запуска | ![Пример 1](images/example_1.png) |

## 📋 Журналы и коды завершения

| Файл / код | Значение |
|---|---|
| `logs\batch_startup.log` | Старт пакетного файла, вывод программы и код завершения |
| `logs\meteor.log` | Основной журнал сортировки, FTP, проверки и аудита |
| `0` | Цикл завершён без операционных ошибок и замечаний аудита |
| `1` | Ошибки операций или проблемы, обнаруженные аудитом |
| `2` | Ошибка конфигурации или недоступный корневой каталог архива |

Основной журнал `meteor.log` ротируется при достижении 5 MiB; хранится до пяти архивных файлов журнала.

При проблеме проверьте доступность `Z:\ENVISAT\METEOP`, параметры FTP в `.env`, последнюю запись `batch_startup.log` и итоговую строку `meteor.log`. На сетевом ресурсе пустая старая папка иногда может оставаться видимой, пока другой пользователь держит её открытой; после закрытия папка удаляется.

## 🔒 Важное замечание о безопасности

Обычный FTP не шифрует учётные данные. Если сервер поддерживает FTPS или SFTP, следует уточнить возможность использования защищённого протокола. Проект не должен содержать настоящие пароли, токены или локальный файл `.env`.

---

<a id="english"></a>

## 🇬🇧 English

## ✅ Project overview

`meteor` runs one processing cycle and exits. The intended automation method is Windows Task Scheduler (`taskschd.msc`).

| Stage | What it does |
|---|---|
| 🗂️ Archive sorting | Scans the existing archive and moves matching TIFF files according to the acquisition date parsed from each filename. |
| 🌐 FTP retrieval | Lists matching files in the configured remote directory and downloads missing files or files with a known size mismatch. |
| 🛡️ Safe download | Writes downloads to a temporary `.part` file and publishes them only after transfer completes and the size is validated when the server reports it. |
| 🔎 Archive audit | Checks snapshot placement, date parsing, temporary downloads and unexpected files. |
| 🧹 Cleanup | Removes empty directories only. Image files on the archive and on FTP are not automatically deleted. |

The project does not process image pixels: GDAL, TIFF compression and email delivery are not required.

## 🗓️ Archive layout

The default archive root is `Z:\ENVISAT\METEOP`. Each period starts on **Tuesday** and ends on the following Monday, inclusive. This keeps snapshots arriving on Monday as the continuation of a pass together with the previous days.

The `Wnn` label is the ISO week number for the period start date (Tuesday). The year directory is calculated from the ISO year of that date.

```text
Z:\ENVISAT\METEOP\
└── 2026\
    ├── W40_2026-09-29_2026-10-05\
    └── W41_2026-10-06_2026-10-12\
```

For example, `METM24_20261012t003301_13586_1_1_BRLK_RLI_log10.tif` is stored in `2026/W41_2026-10-06_2026-10-12/`. Periods are not split at month boundaries. Near New Year, the parent year may differ from the acquisition calendar year because it follows the ISO year of the period start date.

## 🔍 Processing and safety rules

| Situation | Behaviour |
|---|---|
| File is already in its target directory | It is not moved again. |
| A sorting destination with the same filename already exists | Both files are preserved; the conflict is logged and the audit reports the misplaced source. |
| Local file exists and its size matches the FTP size | The download is skipped. |
| FTP reports a size different from the existing local file | The file is downloaded to `.part` and replaces the target only after successful transfer and size validation. |
| FTP size cannot be retrieved for an existing file | The existing local file is not overwritten. |
| A `.part` or unexpected file is found | The audit reports it but does not delete it automatically. |
| `Thumbs.db` is found | Windows thumbnail cache is ignored. |
| Empty directories remain after sorting | Empty directories only are removed. |

The script never deletes the source snapshots on FTP. Audit issues cause a non-zero exit code so an automated run can be flagged.

## 🧰 Technology

| Component | Purpose | Version / requirement |
|---|---|---|
| Python | Processing logic, sorting and FTP client | Python 3.10+; locally verified with 3.14.3 |
| `python-dotenv` | Reads local settings from `.env` | `>=1.0,<2.0` |
| `unittest` | Local tests without FTP or network archive changes | Python standard library |
| Windows Task Scheduler | Daily automation | `taskschd.msc` |
| FTP | Snapshot source | Defaults to `ftp.ntsomz.ru:21` |

## 🚀 Installation

Open CMD and change to the project directory. Create a virtual environment if one does not exist yet:

```bat
cd /d E:\Programming_Work\VScode_Work\meteor
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Edit the local `.env` file and provide the FTP credentials. Do not recreate `.venv` if it is already set up.

🔐 **Never place real credentials in `main.py`, `run_meteor.bat`, this README or any other Git-tracked file.** The real `.env` file is excluded from Git.

## ⚙️ `.env` configuration

| Variable | Default | Description |
|---|---|---|
| `METEOR_FTP_HOST` | `ftp.ntsomz.ru` | FTP host |
| `METEOR_FTP_PORT` | `21` | FTP port |
| `METEOR_FTP_USER` | Not set | FTP username — required |
| `METEOR_FTP_PASSWORD` | Not set | FTP password — required |
| `METEOR_FTP_REMOTE_DIR` | `.` | Remote directory after login; dot means the current directory |
| `METEOR_FTP_TIMEOUT` | `60` | Network timeout in seconds |
| `METEOR_DEST_DIR` | `Z:\ENVISAT\METEOP` | Network archive root |
| `METEOR_FILE_GLOB` | `METM24_*_BRLK_RLI_log10.tif` | Snapshot filename pattern |
| `METEOR_LOG_DIR` | `logs` | Log directory; relative paths are resolved from the project directory |

The default pattern targets Meteor-M BRLK images. Both `.tif` and `.tiff` extensions are recognised.

## ▶️ Run and test

Run local tests — they do not connect to FTP or modify the production network archive:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover filename/date parsing, Tuesday-to-Monday boundaries across month and year changes, `.tif/.tiff`, sorting, filename conflicts and archive audit. The latest local test run passed all **13 tests**.

Run one complete cycle manually:

```bat
.venv\Scripts\python.exe main.py
```

Or use the recommended launcher:

```bat
run_meteor.bat
```

The batch file uses the interpreter from `.venv`, records startup/completion details and returns the Python process exit code.

## 🕒 Windows Task Scheduler

The configured daily task uses the following settings:

| Setting | Value |
|---|---|
| Trigger | Daily at **10:30** |
| Program | `C:\Windows\System32\cmd.exe` |
| Arguments | `/d /c ""<PROJECT_PATH>\run_meteor.bat""` |
| Start in | Project directory, without quotes |
| Account | Windows user with access to FTP and the archive |
| Run mode | Run only when the user is logged on |
| If already running | Do not start a new instance |
| Missed run | Run as soon as possible |

Replace `<PROJECT_PATH>` with the actual project path on your computer. The current local setup uses `E:\Programming_Work\VScode_Work\meteor`.

✅ The scheduled task runs independently of VS Code. You can use other programs while it executes; the project does not need to be open in the editor.

⚠️ `Z:` is a mapped network drive, so the task is configured for the logged-in Windows session where the drive is available. To run after logoff, configure and test the share's UNC path and access permissions; simply switching to a background logon mode is not enough.

After a test run, check both logs. A successful Task Scheduler result is normally shown as `0x0`.

### 🖼️ Example

| Illustration | Repository file |
|---|---|
| Example image | ![Example 1](images/example_1.png) |

## 📋 Logs and exit codes

| File / code | Meaning |
|---|---|
| `logs\batch_startup.log` | Batch startup, program output and exit code |
| `logs\meteor.log` | Main sorting, FTP, validation and audit log |
| `0` | Cycle completed without operational errors or audit issues |
| `1` | Operational errors or issues detected by the audit |
| `2` | Configuration error or unavailable archive root |

The main `meteor.log` rotates at 5 MiB and keeps up to five archived log files.

If a run fails, check access to `Z:\ENVISAT\METEOP`, FTP settings in `.env`, the latest entry in `batch_startup.log` and the final summary in `meteor.log`. On a network share, an old empty directory may remain visible while another user has it open; it can disappear after the open handle is released.

## 🔒 Security note

Plain FTP does not encrypt credentials. If the server supports FTPS or SFTP, consider using a secure protocol. Do not commit real passwords, tokens or the local `.env` file.

---

<a id="contacts"></a>

## 🏢 Контакты / Department contacts

| Русский | English |
|---|---|
| Центр Ледовой и Гидрометеорологической Информации (ЦЛГМИ), Центр «Север» | Center of Ice and Hydrometeorological Information (CIHMI), Center “Sever” |
| Арктический и антарктический научно-исследовательский институт | Arctic and Antarctic Research Institute |
| ФГБУ «ААНИИ», Санкт-Петербург | FSBI “AARI”, St. Petersburg |
| Почта: [sever@aari.ru](mailto:sever@aari.ru) | E-mail: [sever@aari.ru](mailto:sever@aari.ru) |
| Почта: [vvbusev@aari.ru](mailto:vvbusev@aari.ru) | E-mail: [vvbusev@aari.ru](mailto:vvbusev@aari.ru) |
| ![Логотип на русском](images/logo_ru.png) | ![English logo](images/logo_en.png) |

---

<p align="center">
  <img src="https://media.tenor.com/7giYfxCxDaMAAAAM/nasa-nasa-gifs.gif" alt="NASA animated GIF" />
</p>

<p align="center">
  <sub>MIT License · © 2026 Vlad Busev</sub>
</p>
