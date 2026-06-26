import requests
import json
import os
import urllib3
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- НАСТРОЙКИ ---
GRAFANA_URL = "https://grafana.url"
API_KEY = "grafana_key"
LOCAL_EXPORT_PATH = "./grafana_export"

# GitLab настройки
GITLAB_URL = "gitlab.url"
GITLAB_PROJECT = "path/to/repository/backup-dashboards-grafana"
GITLAB_TOKEN = "gitlab_key"
GIT_BRANCH = "main"
REPO_PATH = "./grafana-git-repo"



HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def run_git_command(cmd, cwd=None):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd or REPO_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Git ошибка: {e.stderr}")
        return None

def get_all_alert_rules():
    """Получаем все алерт-рулы через provisioning API"""
    print("🔍 Загружаем все алерт-рулы...")
    url = f"{GRAFANA_URL}/api/v1/provisioning/alert-rules"
    resp = requests.get(url, headers=HEADERS, verify=False)

    if resp.status_code != 200:
        print(f"❌ Ошибка получения алерт-рулов: {resp.status_code} - {resp.text}")
        return []

    rules = resp.json()
    print(f"✅ Найдено алерт-рулов: {len(rules)}")
    return rules

def clean_rule_for_backup(rule):
    """Очищаем правило от служебных полей перед сохранением"""
    # Убираем поля, которые Grafana генерирует автоматически
    fields_to_remove = ['id', 'orgID', 'updated', 'record']

    cleaned_rule = {}
    for key, value in rule.items():
        if key not in fields_to_remove:
            cleaned_rule[key] = value

    return cleaned_rule

def export_alert_rules_to_file(rules, output_path):
    """Сохраняем все правила в один JSON файл"""
    # Очищаем каждое правило
    cleaned_rules = [clean_rule_for_backup(rule) for rule in rules]

    # Создаём структуру с метаданными
    backup_data = {
        "metadata": {
            "exported_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
            "grafana_url": GRAFANA_URL,
            "total_rules": len(cleaned_rules)
        },
        "alert_rules": cleaned_rules
    }

    # Сохраняем в файл
    output_file = Path(output_path) / "alert_rules_backup.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    print(f"💾 Сохранено в: {output_file}")
    return output_file

def setup_git_repo():
    """Настраиваем Git репозиторий (та же логика что и в первом скрипте)"""
    repo_path = Path(REPO_PATH)
    if repo_path.exists() and (repo_path / ".git").exists():
        print("📂 Используем существующий репозиторий...")
        remotes = run_git_command("git remote -v")
        if not remotes or GITLAB_PROJECT not in remotes:
            print(f"➕ Обновляем remote...")
            run_git_command(f"git remote set-url origin https://oauth2:{GITLAB_TOKEN}@{GITLAB_URL}/{GITLAB_PROJECT}.git")
    else:
        print(f"📥 Клонируем репозиторий: {GITLAB_PROJECT}")
        if repo_path.exists():
            shutil.rmtree(repo_path)
        repo_url = f"https://oauth2:{GITLAB_TOKEN}@{GITLAB_URL}/{GITLAB_PROJECT}.git"
        run_git_command(f"git clone {repo_url} {REPO_PATH}", cwd=".")

    gitignore_path = Path(REPO_PATH) / ".gitignore"
    if not gitignore_path.exists():
        with open(gitignore_path, 'w') as f:
            f.write(".DS_Store\nThumbs.db\n*.tmp\n")
    return True

def commit_and_push():
    """Коммитим и пушим изменения"""
    print("\n🔄 Синхронизация с GitLab...")
    run_git_command("git add -A")
    status = run_git_command("git status --porcelain")

    if not status:
        print("✅ Нет изменений для коммита")
        return

    commit_message = f"Update Grafana alert rules backup - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    run_git_command(f'git commit -m "{commit_message}"')
    print(f"✅ Закоммичено: {commit_message}")

    print(f"⬆️  Пушим в ветку: {GIT_BRANCH}...")
    result = run_git_command(f"git push origin HEAD:{GIT_BRANCH}")
    if result is not None:
        print(f"✅ Запушено успешно")
    else:
        print(f"❌ Ошибка при пуше")

def main():
    print("🚀 Бэкап Grafana Alert Rules с интеграцией GitLab...\n")

    # Создаём временную директорию для экспорта
    if Path(LOCAL_EXPORT_PATH).exists():
        shutil.rmtree(LOCAL_EXPORT_PATH)
    Path(LOCAL_EXPORT_PATH).mkdir(exist_ok=True)

    # Получаем все алерт-рулы
    rules = get_all_alert_rules()

    if not rules:
        print("⚠️  Алерт-рулы не найдены, завершаем работу")
        return

    # Экспортируем в файл
    export_alert_rules_to_file(rules, LOCAL_EXPORT_PATH)

    # Работаем с Git
    try:
        setup_git_repo()

        # Копируем файл бэкапа в репо
        print("\n📁 Копируем файл бэкапа в Git репозиторий...")
        src_file = Path(LOCAL_EXPORT_PATH) / "alert_rules_backup.json"
        dst_file = Path(REPO_PATH) / "alert_rules_backup.json"

        if src_file.exists():
            shutil.copy2(src_file, dst_file)
            print(f"✅ Файл скопирован: {dst_file}")

        commit_and_push()

    except Exception as e:
        print(f"❌ Ошибка работы с Git: {e}")
        import traceback
        traceback.print_exc()

    print("\n🎉 Готово!")

if __name__ == "__main__":
    main()
