import pandas as pd
import os
import re
import shutil
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# --- Новые импорты для Google Sheets ---
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials

# --- Конфигурация Google Sheets ---
SPREADSHEET_ID = "1wp4xdCGLda308NeM6RLAX4sFURxvbS3f39jOtWm9m0M"
SHEET_NAME = "Результаты"
CREDENTIALS_FILE = "credentials.json"   # путь к файлу с ключом (лежит в папке со скриптом)

# --- Остальные константы ---
LOG_FILE = "error.log"
LOCAL_BACKUP_FILE = "Свод торги.xlsx"   # необязательный резервный файл

def log_error(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()}: {msg}\n")

# --- Функции для работы с Google Sheets ---
def get_gsheet_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

def load_from_gsheet():
    """Загружает данные из Google Sheets в DataFrame."""
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        df = get_as_dataframe(sheet, evaluate_formulas=True)
        if df.empty:
            return pd.DataFrame()
        # Приводим PLU к строке (как в оригинале)
        if "PLU" in df.columns:
            df["PLU"] = df["PLU"].astype(str)
        return df
    except Exception as e:
        log_error(f"Ошибка загрузки из Google Sheets: {e}")
        print(f"⚠️ Не удалось загрузить данные из Google Sheets: {e}")
        return pd.DataFrame()

def save_to_gsheet(df):
    """Перезаписывает лист Google Sheets данными из DataFrame."""
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        sheet.clear()  # очищаем лист
        set_with_dataframe(sheet, df, include_index=False, resize=True)
        print(f"✅ Данные записаны в Google Sheets: {len(df)} строк")
    except Exception as e:
        log_error(f"Ошибка сохранения в Google Sheets: {e}")
        print(f"❌ Ошибка сохранения в Google Sheets: {e}")
        raise

# --- Оригинальные функции (без изменений) ---

def parse_tender_and_stage(filename, filepath):
    stage = None
    base = re.sub(r'\.xlsx$', '', filename, flags=re.I)
    match = re.search(r'(этап|stage)\s*(\d+)', base, re.I)
    if match:
        tender = base[:match.start()].strip()
        stage = int(match.group(2))
        if stage not in [1, 2, 3, 4]:
            stage = None
    else:
        tender = base
    mod_time = os.path.getmtime(filepath)
    file_date = datetime.fromtimestamp(mod_time).strftime("%d.%m.%Y")
    return tender, stage, file_date

def read_procedure_file(filepath):
    try:
        xl = pd.ExcelFile(filepath)
        sheet_name = None
        for sheet in xl.sheet_names:
            if "сбор" in sheet.lower():
                sheet_name = sheet
                break
        if sheet_name is None:
            raise ValueError(f"В файле {filepath} не найден лист с 'Сбор' в названии.")
        df = pd.read_excel(filepath, sheet_name=sheet_name, header=0)
    except Exception as e:
        raise ValueError(f"Не удалось прочитать файл {filepath}: {e}")

    required = ["Код PLU", "Название PLU", "РЦ доставки", "Количество",
                "Мое предложение", "Срок поставки от", "Срок поставки до"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"В файле {filepath} отсутствуют колонки: {missing}")

    df = df[required].copy()
    df.columns = ["PLU", "Название", "РЦ", "Объем", "Цена", "Период_от", "Период_до"]
    df = df.dropna(subset=["PLU", "РЦ"])
    df["PLU"] = df["PLU"].astype(str)
    df["Цена"] = pd.to_numeric(df["Цена"], errors="coerce")
    df["Период"] = df["Период_от"].astype(str) + " – " + df["Период_до"].astype(str)
    df = df.drop(columns=["Период_от", "Период_до"])
    df = df[df["Цена"].notna()]
    return df.to_dict("records")

def collect_all_data(folder_path):
    all_records = []
    for filename in os.listdir(folder_path):
        if not filename.endswith(".xlsx") or filename == LOCAL_BACKUP_FILE:
            continue
        filepath = os.path.join(folder_path, filename)
        tender, stage, file_date = parse_tender_and_stage(filename, filepath)
        if stage is None:
            print(f"Пропускаем файл (не удалось определить этап): {filename}")
            continue
        try:
            records = read_procedure_file(filepath)
        except Exception as e:
            log_error(str(e))
            print(f"Ошибка при чтении {filename}: {e}")
            continue
        for rec in records:
            rec["Тендер"] = tender
            rec["Этап"] = stage
            rec["Дата_файла"] = file_date
            all_records.append(rec)
        print(f"Обработан файл: {filename}, найдено {len(records)} лотов с ценой")
    if not all_records:
        return pd.DataFrame()
    return pd.DataFrame(all_records)

def prepare_data_for_save(df_all):
    stages = [1, 2, 3, 4]
    stage_dfs = {}
    for s in stages:
        df_s = df_all[df_all["Этап"] == s].copy()
        if not df_s.empty:
            df_s = df_s[["Тендер", "РЦ", "PLU", "Название", "Объем", "Цена", "Период", "Дата_файла"]]
            df_s = df_s.rename(columns={"Цена": f"Цена_этап{s}", "Дата_файла": f"Дата_этап{s}"})
            stage_dfs[s] = df_s
        else:
            stage_dfs[s] = pd.DataFrame(columns=["Тендер", "РЦ", "PLU", "Название", "Объем", f"Цена_этап{s}", f"Дата_этап{s}"])
    merged = stage_dfs[1]
    for s in range(2, 5):
        merged = pd.merge(merged, stage_dfs[s], on=["Тендер", "РЦ", "PLU"], how="outer", suffixes=("", f"_{s}"))
    base_cols = ["Название", "Объем", "Период"]
    for col in base_cols:
        cols = [c for c in merged.columns if c.startswith(col)]
        if cols:
            merged[col] = merged[cols[0]]
            for c in cols[1:]:
                merged[col] = merged[col].combine_first(merged[c])
            merged = merged.drop(columns=[c for c in cols if c != col])
    date_cols = [c for c in merged.columns if c.startswith("Дата_этап")]
    if date_cols:
        merged["Дата торгов"] = merged[date_cols[0]]
        for c in date_cols[1:]:
            merged["Дата торгов"] = merged["Дата торгов"].combine_first(merged[c])
        merged = merged.drop(columns=date_cols)
    for s in stages:
        col_name = f"Цена_этап{s}"
        if col_name in merged.columns:
            merged = merged.rename(columns={col_name: f"Цена (этап {s})"})
    if "Объем выигранный" not in merged.columns:
        merged["Объем выигранный"] = None

    def calc_price_change(row):
        price1 = row.get("Цена (этап 1)")
        if pd.isna(price1):
            return None
        max_stage = 1
        for s in [2, 3, 4]:
            col = f"Цена (этап {s})"
            if col in row and pd.notna(row[col]):
                max_stage = s
        if max_stage == 1:
            return None
        last_price = row.get(f"Цена (этап {max_stage})")
        if pd.isna(last_price):
            return None
        return last_price - price1

    merged["Изменение цены"] = merged.apply(calc_price_change, axis=1)
    if "Название" in merged.columns:
        merged = merged.rename(columns={"Название": "Наименование"})
    return merged

def generate_analysis(row):
    total_vol = row.get("Объем")
    win_vol = row.get("Объем выигранный")
    if pd.isna(total_vol) or total_vol == 0:
        return "Нет объёма"
    if pd.isna(win_vol) or win_vol == 0:
        price1 = row.get("Цена (этап 1)")
        max_stage = 1
        for s in [2, 3, 4]:
            col = f"Цена (этап {s})"
            if col in row and pd.notna(row[col]):
                max_stage = s
        last_price = row.get(f"Цена (этап {max_stage})") if max_stage > 1 else None
        if not pd.isna(price1) and not pd.isna(last_price) and last_price < price1:
            return "❌ Необходимо снижать цену (0% выигрыша)"
        else:
            return "❌ 0% выигрыша – пересмотрите цену"
    percent = (win_vol / total_vol) * 100
    if percent >= 90:
        return f"✅✅ Дали {percent:.0f}% от объёма. Можно немного повысить цену."
    elif percent >= 50:
        return f"✅ Дали {percent:.0f}% от объёма. Отличная цена!"
    elif percent >= 1:
        return f"🟡 Дали {percent:.0f}% от объёма. Можно немного снизить цену."
    else:
        return f"❌ Дали {percent:.0f}% от объёма. Пересмотрите цену."

def update_existing_with_new(existing_df, new_data_df):
    if existing_df.empty:
        df = new_data_df.copy()
        df["Вывод"] = df.apply(generate_analysis, axis=1)
        return df
    key_cols = ["РЦ", "PLU", "Тендер"]
    update_cols = ["Наименование", "Объем", "Период", "Дата торгов",
                   "Цена (этап 1)", "Цена (этап 2)", "Цена (этап 3)", "Цена (этап 4)",
                   "Изменение цены", "Объем выигранный"]
    existing_df = existing_df.copy()
    new_data_df = new_data_df.copy()
    if "Вывод" not in existing_df.columns:
        existing_df["Вывод"] = None
    existing_df["_key"] = existing_df[key_cols[0]].astype(str) + "|" + existing_df[key_cols[1]].astype(str) + "|" + existing_df[key_cols[2]].astype(str)
    new_data_df["_key"] = new_data_df[key_cols[0]].astype(str) + "|" + new_data_df[key_cols[1]].astype(str) + "|" + new_data_df[key_cols[2]].astype(str)
    updated_rows = {}
    for idx, row in existing_df.iterrows():
        updated_rows[row["_key"]] = row.to_dict()
    for idx, new_row in new_data_df.iterrows():
        key = new_row["_key"]
        if key in updated_rows:
            for col in update_cols:
                if col in new_row and pd.notna(new_row[col]):
                    updated_rows[key][col] = new_row[col]
            if "Дата торгов" in new_row and pd.notna(new_row["Дата торгов"]):
                updated_rows[key]["Дата торгов"] = new_row["Дата торгов"]
        else:
            updated_rows[key] = new_row.to_dict()
    result_df = pd.DataFrame.from_dict(updated_rows, orient="index")
    result_df = result_df.drop(columns=["_key"], errors="ignore")
    result_df["Вывод"] = result_df.apply(generate_analysis, axis=1)
    desired_order = ["Дата торгов", "Тендер", "РЦ", "PLU", "Наименование", "Объем",
                     "Цена (этап 1)", "Цена (этап 2)", "Цена (этап 3)", "Цена (этап 4)",
                     "Изменение цены", "Период", "Объем выигранный", "Вывод"]
    other_cols = [col for col in result_df.columns if col not in desired_order]
    final_cols = desired_order + other_cols
    final_cols = [col for col in final_cols if col in result_df.columns]
    result_df = result_df[final_cols]
    return result_df

def is_valid_excel(filepath):
    try:
        pd.read_excel(filepath, sheet_name=0, nrows=1)
        return True
    except Exception:
        return False

# --- ГЛАВНАЯ ФУНКЦИЯ (обновлена) ---
def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"Обработка файлов в папке: {script_dir}")

    # 1. Сбор данных из всех Excel-файлов в папке
    all_data = collect_all_data(script_dir)
    if all_data.empty:
        print("Нет данных для обработки.")
        input("Нажмите Enter для выхода...")
        return

    # 2. Преобразование в формат свода
    new_formatted = prepare_data_for_save(all_data)

    # 3. Загрузка существующих данных из Google Sheets
    print("Загрузка существующих данных из Google Sheets...")
    existing = load_from_gsheet()

    # Если загрузить не удалось или таблица пуста – создаём новый свод
    if existing.empty:
        print("Таблица в Google Sheets пуста или не найдена. Будет создан новый свод.")
        updated_df = new_formatted.copy()
        updated_df["Вывод"] = updated_df.apply(generate_analysis, axis=1)
    else:
        # Приводим типы на всякий случай
        if "PLU" in existing.columns:
            existing["PLU"] = existing["PLU"].astype(str)
        if "Название" in existing.columns and "Наименование" not in existing.columns:
            existing = existing.rename(columns={"Название": "Наименование"})
        if "Снижение" in existing.columns and "Изменение цены" not in existing.columns:
            existing = existing.rename(columns={"Снижение": "Изменение цены"})
        print(f"Найден существующий свод: {len(existing)} записей.")
        updated_df = update_existing_with_new(existing, new_formatted)
        print(f"Обновлено: {len(updated_df)} записей (было {len(existing)}, добавлено/обновлено {len(new_formatted)})")

    # 4. Сортировка и порядок колонок
    updated_df = updated_df.sort_values(["РЦ", "Дата торгов", "PLU"]).reset_index(drop=True)

    desired_order = ["Дата торгов", "Тендер", "РЦ", "PLU", "Наименование", "Объем",
                     "Цена (этап 1)", "Цена (этап 2)", "Цена (этап 3)", "Цена (этап 4)",
                     "Изменение цены", "Период", "Объем выигранный", "Вывод"]
    other_cols = [col for col in updated_df.columns if col not in desired_order]
    final_cols = desired_order + other_cols
    final_cols = [col for col in final_cols if col in updated_df.columns]
    updated_df = updated_df[final_cols]

    # 5. Сохранение в Google Sheets
    try:
        save_to_gsheet(updated_df)
        print("✅ Свод успешно обновлён в Google Sheets.")
    except Exception as e:
        print(f"❌ Ошибка записи в Google Sheets: {e}")
        # Попытка сохранить локальный бэкап на случай ошибки
        try:
            with pd.ExcelWriter(LOCAL_BACKUP_FILE, engine="openpyxl") as writer:
                updated_df.to_excel(writer, sheet_name="Свод", index=False)
            print(f"💾 Свод сохранён локально как {LOCAL_BACKUP_FILE} (на случай ошибки).")
        except Exception as backup_e:
            print(f"❌ Не удалось сохранить даже локальный файл: {backup_e}")

    input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()