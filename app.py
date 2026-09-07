import streamlit as st
import time
from google import genai
from google.genai import errors
from pydantic import BaseModel, Field

st.set_page_config(page_title="まゆみのPFC献立サポーター", layout="centered")

st.title("🥗 PFC献立サポーター")
st.caption("残りの目標数値・ボリューム配分に合わせてAIが献立を提案します。")

# 1. スキーマ定義
class MealItem(BaseModel):
    name: str = Field(description="料理・食材名")
    amount: str = Field(description="分量（例: 150g, 1切れ）")
    p: float = Field(description="タンパク質(g)")
    f: float = Field(description="脂質(g)")
    c: float = Field(description="炭水化物(g)")

class MealPlan(BaseModel):
    meal_type: str = Field(description="朝食、昼食、夕食")
    menu_title: str = Field(description="献立名")
    items: list[MealItem] = Field(description="料理一覧")
    subtotal_p: float = Field(description="小計P(g)")
    subtotal_f: float = Field(description="小計F(g)")
    subtotal_c: float = Field(description="小計C(g)")

class DailySuggestion(BaseModel):
    plans: list[MealPlan] = Field(description="提案された各食事")
    advice: str = Field(description="栄養バランスのアドバイス")

# 2. 残りPFC入力（デフォルト値: P88g, F47g, C160g）
st.subheader("1. 残りのPFCを入力")
col1, col2, col3 = st.columns(3)
with col1:
    rem_p = st.number_input("残り P (g)", min_value=0.0, value=88.0, step=1.0)
with col2:
    rem_f = st.number_input("残り F (g)", min_value=0.0, value=47.0, step=1.0)
with col3:
    rem_c = st.number_input("残り C (g)", min_value=0.0, value=160.0, step=1.0)

# 3. 対象食事とボリューム比重の設定
st.subheader("2. 対象食事とボリュームの比重")
weight_options = ["軽め (小)", "普通 (中)", "重め・しっかり (大)"]

col_b1, col_b2 = st.columns([1, 2])
with col_b1:
    check_b = st.checkbox("朝食")
with col_b2:
    weight_b = st.selectbox("朝食の比重", weight_options, index=0, disabled=not check_b, label_visibility="collapsed")

col_l1, col_l2 = st.columns([1, 2])
with col_l1:
    check_l = st.checkbox("昼食", value=True)
with col_l2:
    weight_l = st.selectbox("昼食の比重", weight_options, index=1, disabled=not check_l, label_visibility="collapsed")

col_d1, col_d2 = st.columns([1, 2])
with col_d1:
    check_d = st.checkbox("夕食", value=True)
with col_d2:
    weight_d = st.selectbox("夕食の比重", weight_options, index=2, disabled=not check_d, label_visibility="collapsed")

target_meals = []
if check_b: target_meals.append(f"朝食（ボリューム: {weight_b}）")
if check_l: target_meals.append(f"昼食（ボリューム: {weight_l}）")
if check_d: target_meals.append(f"夕食（ボリューム: {weight_d}）")

# 4. 使いたい食材
st.subheader("3. 使いたい食材（任意）")
preferred_ingredients = st.text_input("冷蔵庫にある食材など（カンマ区切り）", placeholder="例: 鶏むね肉, 卵, 豆腐, キャベツ")

# 5. 提案ボタン
if st.button("AIに献立を提案してもらう", type="primary", use_container_width=True):
    if not target_meals:
        st.warning("食事を少なくとも1つ選択してください。")
    else:
        with st.spinner("指定食材と配分バランスを考慮して献立を考案中..."):
            api_key = st.secrets["GEMINI_API_KEY"]
            client = genai.Client(api_key=api_key)
            
            prompt = f"""
            あなたはプロの管理栄養士です。以下の条件に合わせて最適な献立を作成してください。
            
            【目標条件】
            ・対象食事と各ボリューム配分:
              {chr(10).join(['  - ' + m for m in target_meals])}
            ・補うべき全体の合計PFC:
              - タンパク質(P): {rem_p}g
              - 脂質(F): {rem_f}g
              - 炭水化物(C): {rem_c}g
            ・優先して使いたい食材: {preferred_ingredients if preferred_ingredients else '特になし'}
            
            【配分と要件】
            ・各食事の「ボリューム（軽め/普通/重め）」の比率を考慮して、全体のPFCを適切に傾斜配分してください。
            ・各食事の合計PFCを足した値が、全体の目標値とほぼ一致（誤差数g以内）するように調整してください。
            ・指定食材がある場合は、無理のない範囲で献立に組み込んでください。
            """

            # 503混雑エラー対策：最大4回まで間隔を空けて自動再試行
            response = None
            max_retries = 4
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=prompt,
                        config={
                            "response_mime_type": "application/json",
                            "response_schema": DailySuggestion,
                        },
                    )
                    break
                except errors.ServerError as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3
                        time.sleep(wait_time)
                        continue
                    st.error("Googleのサーバーが混み合っています。少し待ってから再度お試しください。")
                    raise e

            result = DailySuggestion.model_validate_json(response.text)

            st.success("献立が完成しました！")
            
            for plan in result.plans:
                with st.expander(f"🍽️ {plan.meal_type}：{plan.menu_title}", expanded=True):
                    st.write(f"**PFC小計**: P: {plan.subtotal_p}g / F: {plan.subtotal_f}g / C: {plan.subtotal_c}g")
                    for item in plan.items:
                        st.markdown(f"- **{item.name}** ({item.amount}) : P:{item.p}g, F:{item.f}g, C:{item.c}g")

            st.info(f"💡 **アドバイス**: {result.advice}")
