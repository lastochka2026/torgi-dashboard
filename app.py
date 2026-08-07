import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import os

# --- Новые импорты для Google Sheets ---
import gspread
from gspread_dataframe import get_as_dataframe

st.set_page_config(page_title="Анализ торгов", layout="wide")

# --- Конфигурация Google Sheets ---
SPREADSHEET_ID = "1wp4xdCGLda308NeM6RLAX4sFURxvbS3f39jOtWm9m0M"
SHEET_NAME = "Результаты"

# Словарь контрагентов и их РЦ (без изменений)
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

# --- Функция загрузки данных из Google Sheets ---
@st.cache_data(ttl=600)
def load_data():
    try:
        st.write("Ключи секретов:", st.secrets.keys())   # <--- добавьте эту строку
        if "google" in st.secrets:
        # Проверяем, доступны ли секреты Streamlit (для облака)
        if "google" in st.secrets:
            creds_dict = dict(st.secrets["google"])
            creds = gspread.service_account_from_dict(creds_dict)
        else:
            # Если секретов нет – пробуем использовать локальный файл (для отладки)
            try:
                from oauth2client.service_account import ServiceAccountCredentials
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            except:
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
        
        # --- Дальше идёт ваша оригинальная обработка (без изменений) ---
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

# --- Остальная часть app.py без изменений (кроме имени функции load_data) ---
def main():
    st.title("📊 Анализ торгов")
    df = load_data()
    if df.empty:
        st.stop()

    st.sidebar.header("Фильтры")

    # 1. Дата торгов
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

    # 2. Контрагент
    selected_contragent = st.sidebar.selectbox("Контрагент", options=["Все"] + list(CONTRAGENTS.keys()))
    if selected_contragent != "Все":
        allowed_rc = CONTRAGENTS[selected_contragent]
    else:
        allowed_rc = sorted(df["РЦ"].unique())

    # 3. РЦ
    rc_options = sorted([rc for rc in allowed_rc if rc in df["РЦ"].unique()])
    selected_rc = st.sidebar.multiselect("РЦ", options=rc_options, default=rc_options)

    # 4. Тип торгов
    trade_types = df["Тип торгов"].unique()
    selected_trade_types = st.sidebar.multiselect("Тип торгов", options=trade_types, default=trade_types)

    # 5. Поиск по названию товара
    search_term = st.sidebar.text_input("Поиск по названию товара", "")

    # 6. Выигранный объём
    has_win_vol = st.sidebar.selectbox("Выигранный объём", options=["Все", "Есть выигранный", "Нет выигранного"])

    # 7. Чекбоксы вывода
    col1, col2, col3 = st.sidebar.columns(3)
    with col1:
        show_90_100 = st.checkbox("90-100%", value=True)
    with col2:
        show_50_89 = st.checkbox("50-89%", value=True)
    with col3:
        show_1_49 = st.checkbox("1-49%", value=True)
    show_0 = st.sidebar.checkbox("0%", value=True)

    # 8. Заголовок "Вывод" и текстовый поиск
    st.sidebar.subheader("Вывод")
    search_output = st.sidebar.text_input("Поиск по выводу (текст)", "")

    # Применяем фильтры
    filtered = df.copy()

    # Фильтр по дате
    if isinstance(date_range, tuple) and len(date_range) == 2:
        if date_range[0] and date_range[1]:
            start_dt = pd.to_datetime(date_range[0])
            end_dt = pd.to_datetime(date_range[1])
            filtered["Дата_торгов_dt"] = pd.to_datetime(filtered["Дата торгов"], format="%d.%m.%Y", errors="coerce")
            filtered = filtered[(filtered["Дата_торгов_dt"] >= start_dt) & (filtered["Дата_торгов_dt"] <= end_dt)]
            filtered = filtered.drop(columns=["Дата_торгов_dt"])

    # РЦ
    filtered = filtered[filtered["РЦ"].isin(selected_rc)]

    # Тип торгов
    filtered = filtered[filtered["Тип торгов"].isin(selected_trade_types)]

    # Поиск по названию
    if search_term:
        filtered = filtered[filtered["Наименование"].str.contains(search_term, case=False, na=False)]

    # Выигранный объём
    if has_win_vol == "Есть выигранный":
        filtered = filtered[pd.notna(filtered["Объем выигранный"])]
    elif has_win_vol == "Нет выигранного":
        filtered = filtered[pd.isna(filtered["Объем выигранный"])]

    # Фильтр по чекбоксам (категории вывода)
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

    # Поиск по выводу (текст)
    if search_output:
        filtered = filtered[filtered["Вывод"].str.contains(search_output, case=False, na=False)]

    # ---------- Отображение таблицы ----------
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

    # ---------- Графики ----------
    col1, col2 = st.columns(2)

    with col1:
        if "Объем выигранный" in filtered.columns:
            vol_by_rc = filtered.groupby("РЦ").agg({"Объем": "sum", "Объем выигранный": "sum"}).reset_index()
            fig_vol = px.bar(vol_by_rc, x="РЦ", y=["Объем", "Объем выигранный"],
                             title="Общий и выигранный объём по РЦ",
                             barmode="group", labels={"value": "Объём (кг)", "variable": "Тип"})
            st.plotly_chart(fig_vol, use_container_width=True)
        else:
            st.info("Нет данных о выигранном объёме")

    with col2:
        type_vol = filtered.groupby("Тип торгов").agg({"Объем": "sum"}).reset_index()
        fig_pie = px.pie(type_vol, names="Тип торгов", values="Объем",
                         title="Распределение объёма по типу торгов")
        st.plotly_chart(fig_pie, use_container_width=True)

    # Доля выигранного объёма по РЦ
    if "Объем выигранный" in filtered.columns:
        st.subheader("Доля выигранного объёма по РЦ")
        vol_rc = filtered.groupby("РЦ").agg({"Объем": "sum", "Объем выигранный": "sum"}).reset_index()
        vol_rc["Доля выигранного"] = (vol_rc["Объем выигранный"] / vol_rc["Объем"]) * 100
        fig_donut = px.bar(vol_rc, x="РЦ", y="Доля выигранного",
                           title="% выигранного объёма по РЦ",
                           labels={"Доля выигранного": "% выигранного"})
        st.plotly_chart(fig_donut, use_container_width=True)
    else:
        st.info("Нет данных о выигранном объёме")

    # Сравнение цен
    st.subheader("Сравнение цен (этап 1, последний, выигранная)")
    top_items = filtered.nlargest(10, "Объем")[["Наименование", "Цена (этап 1)", "Цена последнего этапа", "Цена выигранного"]]
    top_melted = top_items.melt(id_vars="Наименование",
                                value_vars=["Цена (этап 1)", "Цена последнего этапа", "Цена выигранного"],
                                var_name="Тип цены", value_name="Цена")
    fig_price = px.bar(top_melted, x="Наименование", y="Цена", color="Тип цены",
                       title="Цены по топ-10 товаров по объёму",
                       barmode="group", labels={"Цена": "Цена (руб.)"})
    st.plotly_chart(fig_price, use_container_width=True)

    # ---------- ДИНАМИКА ЦЕН С ВЫИГРАННЫМ ОБЪЁМОМ ----------
    if not filtered.empty:
        st.subheader("📈 Динамика цен и выигранный объём по товарам")
        product_options = sorted(filtered["Наименование"].unique())
        selected_products = st.multiselect(
            "Выберите товары для графика",
            options=product_options,
            default=product_options[:5] if len(product_options) >= 5 else product_options
        )

        if selected_products:
            dyn_df = filtered[filtered["Наименование"].isin(selected_products)].copy()
            dyn_df["Дата_торгов_dt"] = pd.to_datetime(dyn_df["Дата торгов"], format="%d.%m.%Y", errors="coerce")
            dyn_df = dyn_df.dropna(subset=["Дата_торгов_dt"])
            dyn_df = dyn_df.sort_values("Дата_торгов_dt")

            if not dyn_df.empty:
                fig_dyn = make_subplots(specs=[[{"secondary_y": True}]])

                colors = px.colors.qualitative.Plotly

                for i, product in enumerate(selected_products):
                    prod_data = dyn_df[dyn_df["Наименование"] == product]
                    color = colors[i % len(colors)]

                    # Цена этапа 1 (пунктир)
                    fig_dyn.add_trace(
                        go.Scatter(
                            x=prod_data["Дата_торгов_dt"],
                            y=prod_data["Цена (этап 1)"],
                            mode="lines+markers",
                            name=f"{product} – этап 1",
                            line=dict(color=color, dash="dash"),
                            marker=dict(size=6),
                            legendgroup=product,
                            showlegend=True
                        ),
                        secondary_y=False
                    )

                    # Последняя цена (сплошная)
                    fig_dyn.add_trace(
                        go.Scatter(
                            x=prod_data["Дата_торгов_dt"],
                            y=prod_data["Цена последнего этапа"],
                            mode="lines+markers",
                            name=f"{product} – последняя цена",
                            line=dict(color=color, dash="solid"),
                            marker=dict(size=6),
                            legendgroup=product,
                            showlegend=True
                        ),
                        secondary_y=False
                    )

                    # Выигранный объём (столбцы, правая ось)
                    win_vol = prod_data["Объем выигранный"].fillna(0)
                    fig_dyn.add_trace(
                        go.Bar(
                            x=prod_data["Дата_торгов_dt"],
                            y=win_vol,
                            name=f"{product} – выигранный объём",
                            marker=dict(color=color, opacity=0.4),
                            legendgroup=product,
                            showlegend=False,
                            hovertemplate="%{x|%d.%m.%Y}<br>Выиграно: %{y} кг<extra></extra>"
                        ),
                        secondary_y=True
                    )

                fig_dyn.update_xaxes(title_text="Дата торгов", tickformat="%d.%m.%Y")
                fig_dyn.update_yaxes(title_text="Цена (руб.)", secondary_y=False)
                fig_dyn.update_yaxes(title_text="Выигранный объём (кг)", secondary_y=True)

                fig_dyn.update_layout(
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    hovermode="x unified"
                )

                st.plotly_chart(fig_dyn, use_container_width=True)
            else:
                st.info("Нет данных для выбранных товаров.")
        else:
            st.info("Выберите хотя бы один товар для отображения динамики.")

    # ---------- Статистика по выводу ----------
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