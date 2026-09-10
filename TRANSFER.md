# Перенести библиотеку на другой компьютер

Репозиторий: **https://github.com/mariwars/nouveauraw-offline-library**

Библиотека приватная. Другой компьютер не требует другого аккаунта GitHub: можно войти под `mariwars` и скачать копию. Если будете пользоваться другим аккаунтом, сначала выдайте ему доступ по следующей инструкции.

## 1. Доступ для второго аккаунта GitHub

Выполните эти действия под аккаунтом **mariwars**:

1. Откройте [настройки доступа](https://github.com/mariwars/nouveauraw-offline-library/settings/access).
2. Выберите **Collaborators → Add people** (если страница уже показывает Collaborators, сразу Add people).
3. Найдите точный логин своего второго аккаунта и отправьте приглашение.
4. Войдите под вторым аккаунтом и **примите приглашение** из уведомлений или письма GitHub.
5. Проверьте, что под вторым аккаунтом открывается главная страница репозитория.

После этого можно скачивать. Менять видимость репозитория на Public не требуется. Доступ Collaborator в личном репозитории включает чтение и запись; выдавайте его своему нужному аккаунту.

Если ссылка показывает 404, проверьте, что вошли в правильный аккаунт и приняли приглашение.

Основание: [инструкция GitHub о приглашении участников](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository), [права участника личного репозитория](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository).

## 2. Самый простой способ: через браузер, без установки программ

1. На другом компьютере войдите в GitHub под `mariwars` или приглашённым аккаунтом.
2. Откройте https://github.com/mariwars/nouveauraw-offline-library.
3. Нажмите зелёную кнопку **Code → Download ZIP** и дождитесь окончания загрузки.
4. Распакуйте **весь** ZIP в папку. Не открывайте библиотеку прямо внутри ZIP.
5. Откройте `START_HERE.html` двойным щелчком.

Тексты, фотографии и поиск работают без интернета. Сохраняйте структуру папок: `pages`, `assets` и стартовый файл должны оставаться вместе.

## 3. Скачать командами в Windows

Потребуются Git и GitHub CLI. Если их нет, выполните в PowerShell:

```powershell
winget install --id Git.Git --exact --source winget
winget install --id GitHub.cli --exact --source winget
```

После установки **закройте PowerShell и откройте заново**, чтобы появились команды `git` и `gh`. Подготовьте не менее 4 ГБ свободного места.

Перейдите в папку, где хотите разместить библиотеку, и выполните:

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
gh repo clone mariwars/nouveauraw-offline-library nouveauraw-offline-library -- --depth 1
Set-Location -LiteralPath .\nouveauraw-offline-library
Invoke-Item -LiteralPath .\START_HERE.html
```

При входе выберите нужный аккаунт в браузере. Если CLI показывает одноразовый код, подтвердите его на странице GitHub, которую откроет команда. Если аккаунт уже подключён, проверьте его командой `gh auth status` и при необходимости переключите через `gh auth switch --hostname github.com`.

Команда клонирования скачает сразу все страницы, фотографии и PDF. Папка назначения `nouveauraw-offline-library` должна ещё не существовать; при необходимости выберите другое имя в команде и в следующем `Set-Location`.

Основание: [вход через GitHub CLI](https://cli.github.com/manual/gh_auth_login), [клонирование](https://cli.github.com/manual/gh_repo_clone), [установка GitHub CLI](https://github.com/cli/cli#installation).

## 4. Скачать обновления позже

Из уже скачанной папки:

```powershell
git pull --ff-only
Invoke-Item -LiteralPath .\START_HERE.html
```

Это обновляет копию с GitHub. Скрипт `archive_site.py` для переноса запускать не нужно: он скачивает материалы с первоначального сайта.

## Готовый текст, который можно отправить себе

```text
Моя приватная библиотека NouveauRaw:
https://github.com/mariwars/nouveauraw-offline-library

Войти в GitHub под mariwars или под вторым аккаунтом, которому выдан доступ.
Если аккаунт второй — сначала принять приглашение в репозиторий.
Нажать Code → Download ZIP.
Дождаться загрузки и распаковать архив полностью.
Открыть START_HERE.html в браузере.
Все фотографии находятся внутри скачанной папки, отдельно их скачивать не нужно.
```
