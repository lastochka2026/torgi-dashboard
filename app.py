@st.cache_data(ttl=600)
def load_data():
    try:
        # Отладочный вывод ключей секретов
        st.write("🔑 Ключи секретов:", st.secrets.keys())
        
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes=scope)
        else:
            try:
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            except Exception:
                st.error("❌ Нет доступа к Google Sheets. Добавьте секреты или файл credentials.json")
                return pd.DataFrame()
        
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        
        # Попробуем получить все значения с листа в виде списка списков
        all_values = sheet.get_all_values()
        st.write("🔍 Количество строк на листе:", len(all_values))
        if len(all_values) > 0:
            st.write("🔍 Первые 3 строки:", all_values[:3])
        
        # Теперь читаем как DataFrame
        df = get_as_dataframe(sheet, evaluate_formulas=True)
        st.write("📊 Размер df:", df.shape)
        st.write("📊 Первые 5 строк df:", df.head())
        
        if df.empty:
            st.warning("Таблица в Google Sheets пуста (DataFrame пуст).")
            return pd.DataFrame()
        
        # Приводим PLU к строке
        if "PLU" in df.columns:
            df["PLU"] = df["PLU"].astype(str)
        else:
            st.warning("В таблице нет колонки PLU. Проверьте заголовки.")
            # Всё равно продолжим, но предупредим
        
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