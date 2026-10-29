import pandas as pd
import streamlit as st
from bond_scenarios import scenario_table, validate_bond, comparison_conclusions


def render_bond_scenarios(current_bond):
    st.divider()
    st.markdown("### Nếu lợi suất thay đổi?")
    st.caption("Tính lại toàn bộ dòng tiền với các mức lợi suất mới. Kịch bản 0 là giá lý thuyết theo lợi suất bạn nhập, không phải giá thị trường.")
    shock = st.slider("Kịch bản riêng — thay đổi lợi suất (điểm phần trăm)", -3.0, 3.0, 0.5, .1, key="bond_shock")
    try:
        table = scenario_table(current_bond, (-1,-.5,0,.5,1,round(shock,1)))
        row = table.loc[table["Thay đổi lợi suất (điểm %)"] == round(shock,1)].iloc[0]
        c1,c2,c3 = st.columns(3)
        c1.metric("Lợi suất kịch bản", f'{row["Lợi suất (%/năm)"]:.2f}%')
        c2.metric("Giá sau thay đổi", f'{row["Giá lý thuyết"]:,.0f}')
        c3.metric("So với giá cơ sở", f'{row["Biến động giá (%)"]:+.2f}%')
        st.line_chart(table, x="Lợi suất (%/năm)", y="Giá lý thuyết", color="#88465f")
        with st.expander("Xem số liệu kịch bản & tải CSV"):
            st.dataframe(table.round(3), hide_index=True, width="stretch")
            st.download_button("Xuất kịch bản CSV", table.to_csv(index=False).encode("utf-8-sig"), "bond-scenarios.csv", "text/csv")
    except ValueError as exc:
        st.warning(str(exc))


def render_bond_comparison(current_bond):
    st.caption("Điền từng trái phiếu, rồi bấm Tính so sánh. Biểu đồ cho biết giá thay đổi bao nhiêu % khi lợi suất đổi cùng một mức.")
    st.caption("Hai trái phiếu ban đầu là ví dụ minh họa; bạn có thể sửa thành số liệu của mình.")
    columns = {"code":"Tên", "face_value":"Mệnh giá", "coupon_rate":"Coupon (%/năm)",
               "years":"Kỳ hạn (năm)", "payments_per_year":"Kỳ/năm", "required_yield":"Lợi suất cơ sở (%)", "market_price":"Giá thị trường"}
    if "compare_bonds" not in st.session_state:
        st.session_state.compare_bonds = pd.DataFrame([
            {"Tên":"Ví dụ A", "Mệnh giá":100000., "Coupon (%/năm)":8., "Kỳ hạn (năm)":5., "Kỳ/năm":2,
             "Lợi suất cơ sở (%)":9., "Giá thị trường":96500.},
            {"Tên":"Ví dụ B", "Mệnh giá":100000., "Coupon (%/năm)":10., "Kỳ hạn (năm)":3., "Kỳ/năm":1,
             "Lợi suất cơ sở (%)":8., "Giá thị trường":104500.}])
    st.session_state.setdefault("compare_version",0)
    add_col, copy_col = st.columns(2)
    if add_col.button("+ Thêm trái phiếu", disabled=len(st.session_state.compare_bonds) >= 3):
        example = st.session_state.compare_bonds.iloc[-1].copy()
        example["Tên"] = "Ví dụ C"
        st.session_state.compare_bonds = pd.concat([st.session_state.compare_bonds, example.to_frame().T], ignore_index=True)
        st.session_state.compare_version += 1
        st.rerun()
    if copy_col.button("Thêm từ mục Định giá", disabled=current_bond is None or len(st.session_state.compare_bonds) >= 3,
                       help="Thêm vào ô thứ ba. Bạn có thể sửa một ô có sẵn nếu đã đủ 3 trái phiếu."):
        try:
            b = validate_bond(current_bond)
            if len(st.session_state.compare_bonds) >= 3:
                st.warning("Bảng đã có 3 dòng. Xóa một dòng trước khi thêm.")
            else:
                new = {label:b[key]*100 if key in ("coupon_rate","required_yield") else b[key] for key,label in columns.items()}
                st.session_state.compare_bonds = pd.concat([st.session_state.compare_bonds,pd.DataFrame([new])], ignore_index=True)
                st.session_state.compare_version += 1
                st.rerun()
        except ValueError as exc:
            st.warning(str(exc))
    edited = st.session_state.compare_bonds.copy().reset_index(drop=True)
    for i, col in enumerate(st.columns(len(edited))):
        row = edited.iloc[i]
        prefix = f'compare_{st.session_state.compare_version}_{i}_'
        with col.container(border=True):
            st.markdown(f"#### Trái phiếu {i + 1}")
            edited.at[i, "Tên"] = st.text_input("Tên trái phiếu", str(row["Tên"]), key=prefix+"name")
            edited.at[i, "Coupon (%/năm)"] = st.number_input("Lãi coupon (%/năm)", min_value=0., value=float(row["Coupon (%/năm)"]), step=.1, key=prefix+"coupon")
            edited.at[i, "Kỳ hạn (năm)"] = st.number_input("Số năm còn lại", min_value=.01, max_value=100., value=float(row["Kỳ hạn (năm)"]), step=.5, key=prefix+"years")
            edited.at[i, "Lợi suất cơ sở (%)"] = st.number_input("Lợi suất cơ sở (%/năm)", min_value=0., value=float(row["Lợi suất cơ sở (%)"]), step=.1, key=prefix+"yield",
                                                                help="Lợi suất trước khi áp dụng các kịch bản tăng/giảm.")
            with st.expander("Mệnh giá & kỳ trả lãi"):
                edited.at[i, "Mệnh giá"] = st.number_input("Mệnh giá", min_value=1., value=float(row["Mệnh giá"]), step=1000., key=prefix+"face")
                edited.at[i, "Kỳ/năm"] = st.selectbox("Số lần trả lãi / năm", [1,2,4,12], index=[1,2,4,12].index(int(row["Kỳ/năm"])), key=prefix+"frequency")
            st.caption(f'Mệnh giá {float(edited.at[i, "Mệnh giá"]):,.0f} · Trả lãi {int(edited.at[i, "Kỳ/năm"])} lần/năm')
            if st.button("Bỏ trái phiếu này", key=prefix+"remove", disabled=len(edited)<=2):
                st.session_state.compare_bonds = edited.drop(i).reset_index(drop=True)
                st.session_state.compare_version += 1
                st.rerun()
    st.session_state.compare_bonds = edited
    if st.button("Tính so sánh", type="primary"):
        try:
            if not 2 <= len(edited) <= 3:
                raise ValueError("Nhập từ 2 đến 3 trái phiếu để so sánh.")
            tables=[]
            for i,row in edited.iterrows():
                b = {key:row[label]/100 if key in ("coupon_rate","required_yield") else row[label] for key,label in columns.items()}
                b["code"] = f'{i+1}. {b["code"]}'
                tables.append(scenario_table(b))
            st.session_state.bond_comparison_result = (edited.to_json(), pd.concat(tables, ignore_index=True))
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
    result = st.session_state.get("bond_comparison_result")
    if result and result[0] == edited.to_json():
        comparison = result[1]
        st.line_chart(comparison, x="Thay đổi lợi suất (điểm %)", y="Biến động giá (%)", color="Trái phiếu")
        st.markdown("#### Kết luận sơ bộ")
        for conclusion in comparison_conclusions(comparison):
            st.markdown(conclusion.replace(". ", "\\. ", 1) if conclusion[:1].isdigit() else conclusion)
        with st.expander("Xem bảng số liệu & tải CSV"):
            st.dataframe(comparison.round(3), hide_index=True, width="stretch")
            st.download_button("Xuất bảng so sánh", comparison.to_csv(index=False).encode("utf-8-sig"), "bond-comparison.csv", "text/csv")
    elif result:
        st.info("Bạn đã sửa thông số. Bấm Tính so sánh để cập nhật biểu đồ và kết luận.")
    st.caption("Chỉ áp dụng coupon cố định, các kỳ thanh toán đều và dịch chuyển lợi suất song song. Không mô phỏng vỡ nợ, thuế, lãi tích lũy hoặc mua lại trước hạn.")
