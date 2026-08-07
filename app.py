@st.cache_data(ttl=600)
def load_data():
    try:
        # Отладочный вывод – посмотрим, какие ключи есть в секретах
        st.write("🔑 Ключи секретов:", st.secrets.keys())
        
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            # Используем oauth2client для создания учётных данных из словаря
            from oauth2client.service_account import ServiceAccountCredentials
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes=scope)
        else:
            # Если секретов нет – пробуем использовать локальный файл (для отладки)
            try:
                from oauth2client.service_account import ServiceAccountCredentials
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            except Exception:
                st.error("❌ Нет доступа к Google Sheets. Добавьте секреты или файл credentials.json")
                return pd.DataFrame()
        
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        df = get_as_dataframe(sheet, evaluate_formulas=True)
        
        if df.empty:
            st.warning("Таблица в Google Sheets пуста.")
            return pd.DataFrame()
        
        # Приводим PLU к строке
        if "PLU" in df.columns:
            df["PLU"] = df["PLU"].astype(str)
        else:
            st.warning("В таблице нет колонки PLU")
            return pd.DataFrame()
        
        # --- Обработка периода и типа торгов (без изменений) ---
        def parse_period(period_str):
            if pd.isna(period_str):
                return None, None, None
            parts = period_str.split(" – ")
            if len(parts) == 2:
                try:
                    start = datetime.strptime(parts[0].strip(), "%d.%m.%Y")
                    end = datetime.strptime(parts[1].strip(), "%d.%m.%Y")
                    duration = (end - start).days
                    return start, end, duration
                except:
                    return None, None, None
            return None, None, None

        df[["Дата_начала", "Дата_окончания", "Длительность"]] = df["Период"].apply(
            lambda x: pd.Series(parse_period(x))
        )

        def get_trade_type(duration):
            if pd.isna(duration):
                return "Неизвестно"
            elif duration <= 4:
                return "Дефицит"
            else:
                return "Основные"
        df["Тип торгов"] = df["Длительность"].apply(get_trade_type)

        price_cols = ["Цена (этап 1)", "Цена (этап 2)", "Цена (этап 3)", "Цена (этап 4)"]
        existing_price_cols = [col for col in price_cols if col in df.columns]
        if existing_price_cols:
            def get_last_price(row):
                last_val = None
                for col in reversed(existing_price_cols):
                    if pd.notna(row[col]):
                        last_val = row[col]
                        break
                return last_val
            df["Цена последнего этапа"] = df.apply(get_last_price, axis=1)
        else:
            df["Цена последнего этапа"] = None

        if "Объем выигранный" in df.columns:
            df["Цена выигранного"] = df.apply(
                lambda row: row["Цена последнего этапа"] if pd.notna(row.get("Объем выигранный")) else None,
                axis=1
            )
        else:
            df["Цена выигранного"] = None

        return df

    except Exception as e:
        st.error(f"❌ Ошибка загрузки из Google Sheets: {e}")
        return pd.DataFrame()