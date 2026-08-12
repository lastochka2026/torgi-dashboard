import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import os

import gspread
from gspread_dataframe import get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Анализ торгов", layout="wide")

# --- Конфигурация Google Sheets ---
SPREADSHEET_ID = "1wp4xdCGLda308NeM6RLAX4sFURxvbS3f39jOtWm9m0M"
SHEET_NAME = "Результаты"

# Словарь контрагентов и их РЦ
CONTRAGENTS = {
    "ТСЧ Чижик": [
        "РЦ Пермь", "РЦ Уфа", "РЦ Екатеринбург", "РЦ Челябинск",
        "РЦ Казань", "РЦ Самара", "РЦ Саратов", "РЦ Волгоград",
        "РЦ Ростов-на-Дону", "РЦ Краснодар",
        "Группа РЦ: РЦ Воронеж,2PL РЦ Воронеж Холодный",
        "РЦ Воронеж", "2PL РЦ Воронеж Холодный",
        "РЦ Дзержинск", "РЦ Ярославль", "РЦ Падиково",
        "РЦ Литвиново", "РЦ Валищево", "РЦ Купавна"
    ],
    "АО Перекресток": [
        "РЦ СЛК", "РЦ Х Нижний Новгород", "РЦ Софьино ФРОВ",
        "РЦ Санкт-Петербург", "РЦ Х Воронеж", "РЦ Х Адыгея"
    ],
    "Пятерочка": [
        "Группа РЦ: РЦ 5 Южный Адыгея,РЦ 5 Краснодар",
        "Группа РЦ: РЦ Кузнецк-Алкоголь,РЦ Саратов-Алкоголь",
        "РЦ 5 Волгоград", "РЦ 5 Краснодар", "РЦ 5 Курск-Алкоголь",
        "РЦ 5 Невинномысск-Алкоголь", "РЦ 5 Оренбург Север",
        "РЦ 5 Пермь 2", "РЦ 5 Ростов Алкоголь 2",
        "РЦ 5 Самара", "РЦ 5 Тамбов", "РЦ 5 Южный Адыгея",
        "РЦ Кузнецк-Алкоголь", "РЦ Рамонь-Алкоголь",
        "РЦ Саратов-Алкоголь", "РЦ УФА Сигма-Алкоголь"
    ]
}

@st.cache_data(ttl=600)
def load_data():
    try:
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes=scope)
        else:
            # Для локальной отладки (если есть файл credentials.json)
            try:
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
        
        if "PLU" in df.columns:
            df["PLU"] = df["PLU"].astype(str)
        
        # Обработка периода и типа торгов
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

def main():
    st.title("📊 Анализ торгов")
    df = load_data()
    if df.empty:
        st.stop()

    st.sidebar.header("Фильтры")

    all_dates = pd.to_datetime(df["Дата торгов"], format="%d.%m.%Y", errors="coerce")
    min_date = all_dates.min()
    max_date = all_dates.max()
    if pd.isna(min_date) or pd.isna(max_date):
        st.sidebar.warning("Нет данных о датах торгов")
        date_range = (None, None)
    else:
        date_range = st.sidebar.date_input(
            "Дата торгов",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD.MM.YYYY"
        )

    selected_contragent = st.sidebar.selectbox("Контрагент", options=["Все"] + list(CONTRAGENTS.keys()))
    if selected_contragent != "Все":
        allowed_rc = CONTRAGENTS[selected_contragent]
    else:
        allowed_rc = sorted(df["РЦ"].unique())

    rc_options = sorted([rc for rc in allowed_rc if rc in df["РЦ"].unique()])
    selected_rc = st.sidebar.multiselect("РЦ", options=rc_options, default=rc_options)

    trade_types = df["Тип торгов"].unique()
    selected_trade_types = st.sidebar.multiselect("Тип торгов", options=trade_types, default=trade_types)

    search_term = st.sidebar.text_input("Поиск по названию товара", "")

    has_win_vol = st.sidebar.selectbox("Выигранный объём", options=["Все", "Есть выигранный", "Нет выигранного"])

    col1, col2, col3 = st.sidebar.columns(3)
    with col1:
        show_90_100 = st.checkbox("90-100%", value=True)
    with col2:
        show_50_89 = st.checkbox("50-89%", value=True)
    with col3:
        show_1_49 = st.checkbox("1-49%", value=True)
    show_0 = st.sidebar.checkbox("0%", value=True)

    st.sidebar.subheader("Вывод")
    search_output = st.sidebar.text_input("Поиск по выводу (текст)", "")

    filtered = df.copy()

    if isinstance(date_range, tuple) and len(date_range) == 2:
        if date_range[0] and date_range[1]:
            start_dt = pd.to_datetime(date_range[0])
            end_dt = pd.to_datetime(date_range[1])
            filtered["Дата_торгов_dt"] = pd.to_datetime(filtered["Дата торгов"], format="%d.%m.%Y", errors="coerce")
            filtered = filtered[(filtered["Дата_торгов_dt"] >= start_dt) & (filtered["Дата_торгов_dt"] <= end_dt)]
            filtered = filtered.drop(columns=["Дата_торгов_dt"])

    filtered = filtered[filtered["РЦ"].isin(selected_rc)]
    filtered = filtered[filtered["Тип торгов"].isin(selected_trade_types)]

    if search_term:
        filtered = filtered[filtered["Наименование"].str.contains(search_term, case=False, na=False)]

    if has_win_vol == "Есть выигранный":
        filtered = filtered[pd.notna(filtered["Объем выигранный"])]
    elif has_win_vol == "Нет выигранного":
        filtered = filtered[pd.isna(filtered["Объем выигранный"])]

    conditions = []
    if show_90_100:
        conditions.append(filtered["Вывод"].str.contains("✅✅", na=False))
    if show_50_89:
        conditions.append(filtered["Вывод"].str.contains("✅", na=False) & ~filtered["Вывод"].str.contains("✅✅", na=False))
    if show_1_49:
        conditions.append(filtered["Вывод"].str.contains("🟡", na=False))
    if show_0:
        conditions.append(filtered["Вывод"].str.contains("❌", na=False))
    if conditions:
        filtered = filtered[pd.concat(conditions, axis=1).any(axis=1)]

    if search_output:
        filtered = filtered[filtered["Вывод"].str.contains(search_output, case=False, na=False)]

    st.subheader("Отфильтрованные данные")
    display_cols = ["Дата торгов", "Тип торгов", "РЦ", "Наименование", "Объем",
                    "Цена (этап 1)", "Цена последнего этапа", "Цена выигранного",
                    "Объем выигранный", "Вывод", "Период"]
    display_cols = [col for col in display_cols if col in filtered.columns]

    column_config = {}
    if "Вывод" in display_cols:
        column_config["Вывод"] = st.column_config.TextColumn(width="large")

    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config=column_config
    )

    col1, col2 = st.columns(2)

    with col1:
        # ---- График: Общий объём с разбивкой на выигранный и невыигранный (stacked) ----
        if "Объем выигранный" in filtered.columns:
            # Создаём копию данных для группировки
            plot_data = filtered.copy()
            
            # Добавляем колонку "Невыигранный" = Объем - Объем выигранный (заменяем NA на 0)
            plot_data["Невыигранный"] = plot_data["Объем"] - plot_data["Объем выигранный"].fillna(0)
            
            # Группируем по РЦ: суммируем общий объём (для справки), но для стека нужно разбить по категориям
            # Создаём три категории: Невыигранный, и каждый товар (выигранный)
            # Для этого нужно собрать данные в формате: РЦ, Категория, Объём
            
            # Сначала выделим выигранные строки
            won_rows = plot_data[plot_data["Объем выигранный"].notna() & (plot_data["Объем выигранный"] > 0)]
            # Невыигранные строки – все остальные (или с нулевым выигрышем)
            non_won_rows = plot_data[(plot_data["Объем выигранный"].isna()) | (plot_data["Объем выигранный"] == 0)]
            
            # Для стекового графика нам нужен длинный формат: РЦ, Категория, Объём
            # Категории: "Невыигранный" и названия товаров (только для выигранных)
            
            # Группируем невыигранные объёмы по РЦ
            if not non_won_rows.empty:
                non_won_agg = non_won_rows.groupby("РЦ")["Невыигранный"].sum().reset_index()
                non_won_agg["Категория"] = "Невыигранный"
                non_won_agg = non_won_agg.rename(columns={"Невыигранный": "Объём"})
            else:
                non_won_agg = pd.DataFrame(columns=["РЦ", "Категория", "Объём"])
            
            # Группируем выигранные объёмы по РЦ и товару
            if not won_rows.empty:
                won_agg = won_rows.groupby(["РЦ", "Наименование"], as_index=False)["Объем выигранный"].sum()
                won_agg = won_agg.rename(columns={"Наименование": "Категория", "Объем выигранный": "Объём"})
            else:
                won_agg = pd.DataFrame(columns=["РЦ", "Категория", "Объём"])
            
            # Объединяем
            plot_df = pd.concat([non_won_agg, won_agg], ignore_index=True)
            
            # Упорядочиваем категории: сначала "Невыигранный", затем товары по убыванию объёма
            # Чтобы серый был внизу, а цветные – сверху
            # В стеке порядок определяется порядком в данных – снизу вверх, поэтому лучше сначала "Невыигранный", потом товары
            # Но товары должны быть отсортированы по убыванию, чтобы большие сегменты были снизу среди цветных
            # Мы отсортируем так: сначала "Невыигранный", затем товары по убыванию объёма в рамках каждого РЦ? Но это сложно.
            # Проще оставить как есть – порядок не критичен.
            
            # Строим стековый график
            fig_stack = px.bar(plot_df, 
                               x="РЦ", 
                               y="Объём", 
                               color="Категория",
                               title="Общий объём по РЦ (невыигранный + выигранный по товарам)",
                               barmode="stack",
                               labels={"Объём": "Объём (кг)"},
                               color_discrete_map={"Невыигранный": "#D3D3D3"})  # светло-серый для невыигранного
            
            # Для товаров цвета назначаются автоматически
            st.plotly_chart(fig_stack, use_container_width=True)
            
            # Легенда – она уже есть в графике
        else:
            st.info("Нет данных о выигранном объёме")

    with col2:
        # ---- Список выигранных товаров по РЦ (таблица с цветами) ----
        if "Объем выигранный" in filtered.columns:
            won_df = filtered[filtered["Объем выигранный"].notna() & (filtered["Объем выигранный"] > 0)]
            if not won_df.empty:
                # Группируем по РЦ и товару
                won_by_rc_item = won_df.groupby(["РЦ", "Наименование"], as_index=False)["Объем выигранный"].sum()
                # Сортируем по РЦ и убыванию объёма
                won_by_rc_item = won_by_rc_item.sort_values(["РЦ", "Объем выигранный"], ascending=[True, False])
                # Преобразуем в сводную таблицу: строки – РЦ, колонки – товары, значения – объём
                pivot = won_by_rc_item.pivot(index="РЦ", columns="Наименование", values="Объем выигранный").fillna(0)
                # Покажем эту таблицу в виде цветной таблицы? 
                # Лучше просто показать список товаров с цветами, как вы просили – справа список.
                # Можно сделать две колонки: "РЦ" и "Товары (объём)".
                # Сгруппируем товары в строку для каждого РЦ
                grouped = won_by_rc_item.groupby("РЦ").apply(
                    lambda x: ", ".join([f"{row['Наименование']} ({row['Объем выигранный']:.0f} кг)" 
                                         for _, row in x.iterrows()])
                ).reset_index(name="Выигранные товары")
                
                st.subheader("📦 Выигранные товары по РЦ")
                st.dataframe(grouped, use_container_width=True, hide_index=True)
            else:
                st.info("Нет выигранных позиций.")
        else:
            st.info("Нет данных о выигранном объёме")

    st.subheader("📊 Распределение по выводу")
    if "Вывод" in filtered.columns and not filtered.empty:
        def extract_category(text):
            if pd.isna(text):
                return "Нет данных"
            if "✅✅" in text:
                return "90-100% ✅✅"
            elif "✅" in text:
                return "50-89% ✅"
            elif "🟡" in text:
                return "1-49% 🟡"
            elif "❌" in text:
                return "0% ❌"
            else:
                return "Другое"
        filtered["Категория вывода"] = filtered["Вывод"].apply(extract_category)

        cat_counts = filtered["Категория вывода"].value_counts().reset_index()
        cat_counts.columns = ["Категория", "Количество строк"]
        fig_cat = px.bar(cat_counts, x="Категория", y="Количество строк",
                         title="Количество строк по категориям вывода",
                         color="Категория", text_auto=True)
        st.plotly_chart(fig_cat, use_container_width=True)

        vol_by_cat = filtered.groupby("Категория вывода").agg({"Объем": "sum"}).reset_index()
        fig_vol_cat = px.pie(vol_by_cat, names="Категория вывода", values="Объем",
                             title="Объём (кг) по категориям вывода")
        st.plotly_chart(fig_vol_cat, use_container_width=True)
    else:
        st.info("Нет данных для отображения статистики по выводу")

if __name__ == "__main__":
    main()