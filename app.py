    # ---------- ДИНАМИКА ВЫИГРАННОГО ОБЪЁМА ПО ДАТАМ (с разбивкой по типам и тултипом по РЦ) ----------
    st.subheader("📈 Динамика выигранного объёма по датам")
    if "Объем выигранный" in filtered.columns:
        won_over_time = filtered[filtered["Объем выигранный"].notna() & (filtered["Объем выигранный"] > 0)]
        if not won_over_time.empty:
            # Группируем по дате и типу торгов, суммируем выигранный объём
            won_by_date_type = won_over_time.groupby(["Дата торгов", "Тип торгов"], as_index=False)["Объем выигранный"].sum()
            # Преобразуем дату в datetime для правильного порядка
            won_by_date_type["Дата"] = pd.to_datetime(won_by_date_type["Дата торгов"], format="%d.%m.%Y")
            won_by_date_type = won_by_date_type.sort_values("Дата")
            
            # Для тултипа: собираем информацию по РЦ для каждой даты
            # Создаём словарь: дата -> строка с перечнем РЦ и объёмов
            rc_details = {}
            for date in won_over_time["Дата торгов"].unique():
                df_day = won_over_time[won_over_time["Дата торгов"] == date]
                # Группируем по РЦ и типу, чтобы показать в тултипе
                rc_summary = df_day.groupby(["РЦ", "Тип торгов"])["Объем выигранный"].sum().reset_index()
                lines = []
                for _, row in rc_summary.iterrows():
                    lines.append(f"{row['РЦ']} ({row['Тип торгов']}): {row['Объем выигранный']:.0f} кг")
                rc_details[date] = "<br>".join(lines)
            
            # Добавляем колонку с текстом для тултипа
            won_by_date_type["РЦ_детали"] = won_by_date_type["Дата торгов"].map(rc_details)
            
            # Строим стековый график: по оси X – дата, по Y – объём, цвет – тип торгов
            fig_daily = px.bar(won_by_date_type, 
                               x="Дата", 
                               y="Объем выигранный", 
                               color="Тип торгов",
                               title="Выигранный объём по дням (с разбивкой по типам)",
                               labels={"Объем выигранный": "Выигранный объём (кг)"},
                               barmode="stack",
                               color_discrete_map={"Дефицит": "#FF6B6B", "Основные": "#4ECDC4"}  # красный и бирюзовый
                               )
            # Добавляем тултип с деталями по РЦ
            fig_daily.update_traces(
                hovertemplate="<b>%{x|%d.%m.%Y}</b><br>" +
                              "Тип: %{color}<br>" +
                              "Объём: %{y:,.0f} кг<br>" +
                              "<extra></extra>"
            )
            # Добавляем общие подписи над столбцами (суммарный объём за день)
            # Для этого нужно вычислить сумму по датам
            total_by_date = won_by_date_type.groupby("Дата")["Объем выигранный"].sum().reset_index()
            # Добавляем текстовые аннотации
            for i, row in total_by_date.iterrows():
                fig_daily.add_annotation(
                    x=row["Дата"],
                    y=row["Объем выигранный"],
                    text=f"{row['Объем выигранный']:.0f} кг",
                    showarrow=False,
                    font=dict(size=10, color="black"),
                    yshift=5
                )
            
            st.plotly_chart(fig_daily, use_container_width=True)
        else:
            st.info("Нет выигранных позиций для отображения динамики по датам.")
    else:
        st.info("Нет данных о выигранном объёме")