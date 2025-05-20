import streamlit as st
from dashscope import Application
from http import HTTPStatus
import os
import re
import sys
import json
import pandas as pd
from typing import Dict, Callable, List, Any

# 页面设置
st.set_page_config(page_title="Dior HR Assistant", page_icon=":robot:")
st.title("🤖 Dior HR Bot")
st.caption("Powered by Qwen Max through Alibaba Cloud Bailian Platform")

# ===== 配置区 =====
with st.sidebar:
    st.image(f'images/截屏2025-05-09 17.19.08.png', width=150)
    st.header("About This Assistant", divider="gray")
    st.caption("Dior Couture | HR")
    st.write("""
    **Welcome to Dior HR Assistant**
    \nThis intelligent assistant is designed to provides instant answers to HR-related inquiries.
    """)

    st.header("Configuration")
    app_id = st.text_input("Bailian App ID", help="Your Bailian application ID")
    api_key = st.text_input("API Key", type="password", help="Bailian API secret key")

    with st.expander("Advanced Parameters"):
        temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.1)
        top_p = st.slider("Top P", 0.0, 1.0, 0.9, 0.1)
        max_tokens = st.number_input("Max Tokens", min_value=1, max_value=4096, value=1024)

    # 侧边栏按钮：控制年假计算器显示/隐藏
    if "show_leave_calculator" not in st.session_state:
        st.session_state.show_leave_calculator = False
    if st.button(
        "❌ Hide Annual Leave Calculator" if st.session_state.show_leave_calculator else "📅 Show Annual Leave Calculator",
        key="toggle_leave_calculator"
    ):
        st.session_state.show_leave_calculator = not st.session_state.show_leave_calculator
        st.rerun()

    st.divider()
    st.caption("© 2025 Dior HR Assistant")

# ===== 聊天区初始化 =====
if not api_key or not app_id:
    st.warning("⚠️ Please provide App ID and API Key", icon="🔑")
    # 不阻断计算器显示，仅阻断聊天功能
    # st.stop()

# 初始化会话状态
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Bonjour! How can I help you with HR inquiries today?"}]
if "doc_references" not in st.session_state:
    st.session_state.doc_references = {}
if "leave_calculator_state" not in st.session_state:
    st.session_state.leave_calculator_state = {
        "job_category": "",
        "years_service": 0,
        "result": None
    }

# 辅助函数 - 显示文档引用
def show_references(doc_references):
    st.divider()
    st.subheader("📚 References")
    for i, reference in enumerate(doc_references):
        if isinstance(reference, dict):
            for k, v in reference.items():
                st.caption(f"Reference {k}: {v}")
        else:
            st.caption(f"Reference {i + 1}: {reference}")
    with st.expander("🖼️ View Related Images"):
        for reference in doc_references:
            if isinstance(reference, dict):
                for k, doc_name in reference.items():
                    st.image(f'images/{doc_name}.png', caption=doc_name, use_container_width=True)
            else:
                st.image(f'images/{reference}.png', caption=reference, use_container_width=True)

# 聊天机器人类
class ChatBot:
    def __init__(self, api_key: str, app_id: str):
        self.api_key = api_key
        self.app_id = app_id
        self.messages = []

    def ask(self, message: str, stream_callback: Callable[[str], None] = None) -> Dict:
        if len(self.messages) >= 7:
            self.messages.pop(1)  # 保留首尾，仅删除中间对话（示例逻辑，可根据需求调整）
        
        self.messages.append({"role": "user", "content": message})
        responses = Application.call(
            api_key=self.api_key,
            app_id=self.app_id,
            messages=self.messages,
            prompt=message,
            stream=True,
            flow_stream_mode="agent_format"),
            incremental_output=True
        )
        
        full_rsp = ""
        doc_references = []
        json_pattern = re.compile(r'({.*?})$', re.DOTALL)  # 匹配末尾的 JSON 结构
        
        for response in responses:
            if response.status_code != HTTPStatus.OK:
                print(f"Request failed: {response.message}")
                continue
            
            output_text = response.output.text or ""
            
            # 尝试提取 JSON 部分（假设 JSON 位于文本末尾）
            match = json_pattern.search(output_text)
            if match:
                json_str = match.group(1)
                natural_text = output_text[:match.start()].strip()  # 自然语言部分
                try:
                    json_data = json.loads(json_str)
                    full_rsp += natural_text  # 先添加自然语言内容
                    
                    # 提取文档引用（处理列表或字符串情况）
                    refs = json_data.get("doc_references", [])
                    if isinstance(refs, str):
                        refs = json.loads(refs) if refs else []
                    doc_references = refs
                    
                    # 处理结果字段（若存在）
                    result = json_data.get("result", "")
                    if result:
                        full_rsp += result
                except json.JSONDecodeError:
                    full_rsp += output_text  # 解析失败时 fallback 至原始文本
            else:
                full_rsp += output_text  # 无 JSON 时直接累加文本
            
            # 流式输出处理
            if stream_callback and output_text:
                stream_callback(output_text)
            print(output_text, end="", flush=True)
        
        # 清理可能残留的 JSON 标记（如首尾括号/逗号）
        full_rsp = re.sub(r'^[\{\",]|[\}\",]$', '', full_rsp).strip()
        
        # 确保文档引用为列表类型
        if not isinstance(doc_references, list):
            doc_references = [doc_references] if doc_references else []
        
        # 存储对话历史（包含文档引用）
        self.messages.append({
            "role": "assistant",
            "content": full_rsp,
            "doc_references": doc_references
        })
        return {"full_rsp": full_rsp, "doc_references": doc_references}

# 初始化聊天机器人
if "chatbot" not in st.session_state and api_key and app_id:
    st.session_state.chatbot = ChatBot(api_key, app_id)

# 显示历史消息
for msg in st.session_state.messages:
    avatar = "🤖" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("doc_references"):
            show_references(msg["doc_references"])

# 用户输入处理
if prompt := st.chat_input("Ask a question about HR policies..."):
    if api_key and app_id:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🤖"):
            message_placeholder = st.empty()
            resp_container = [""]
            def stream_callback(chunk: str) -> None:
                resp_container[0] += chunk
                message_placeholder.markdown(resp_container[0] + "▌")
            try:
                response = st.session_state.chatbot.ask(prompt, stream_callback)
                full_response = response["full_rsp"]
                doc_references = response["doc_references"]
                
                # 添加合规性尾部提示
                hr_compliant_response = f"{full_response}\n\n---\n*For further HR assistance, contact your local HR representative.*"
                message_placeholder.markdown(hr_compliant_response)
                
                if doc_references:
                    show_references(doc_references)
                
                # 更新会话状态
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": hr_compliant_response,
                    "doc_references": doc_references
                })
            except Exception as e:
                message_placeholder.error(f"⚠️ Error: {str(e)}")

# ===== 年假计算器模块 =====
if st.session_state.show_leave_calculator:
    st.divider()
    st.header("📅 Annual Leave Calculator", divider="gray")
    
    options = [
        "Retail and HO General Staffs & Supervisors",
        "Retail and HO Assistant Managers",
        "Retail and HO Managers (including Senior Boutique Managers)",
        "Sr. Flagship Boutique Manager/ Area Manager",
        "Associate Directors / Directors and above"
    ]
    
    current_value = st.session_state.leave_calculator_state["job_category"]
    current_index = options.index(current_value) if current_value in options else 0
    
    st.session_state.leave_calculator_state["job_category"] = st.selectbox(
        "Job Category",
        options=options,
        key="annual_leave_category_select",
        index=current_index
    )

    st.session_state.leave_calculator_state["years_service"] = st.number_input(
        "Years of Service",
        min_value=0,
        max_value=50,
        value=st.session_state.leave_calculator_state["years_service"],
        key="annual_leave_years_input",
    )

    def calculate_leave():
        category = st.session_state.leave_calculator_state["job_category"]
        years = st.session_state.leave_calculator_state["years_service"]
        
        base_mapping = {
            "Retail and HO General Staffs & Supervisors": 10,
            "Retail and HO Assistant Managers": 12,
            "Retail and HO Managers (including Senior Boutique Managers)": 15,
            "Sr. Flagship Boutique Manager/ Area Manager": 16,
            "Associate Directors / Directors and above": 20
        }
        base = base_mapping.get(category, 0)
        
        bonus = 0
        if years >= 2:
            bonus += 2
            if years >= 5:
                if category in ["Associate Directors / Directors and above", "Sr. Flagship Boutique Manager/ Area Manager"]:
                    bonus += 1 
                else:
                    bonus += 3 
        
        cap_mapping = {
            "Retail and HO General Staffs & Supervisors": 15,
            "Retail and HO Assistant Managers": 17,
            "Retail and HO Managers (including Senior Boutique Managers)": 20,
            "Sr. Flagship Boutique Manager/ Area Manager": 21,
            "Associate Directors / Directors and above": 23
        }
        cap = cap_mapping.get(category, 0)
        total = min(base + bonus, cap)
        return {
            "base_leave": base,
            "service_bonus": bonus,
            "total_leave": total,
            "leave_cap": cap
        }

    if st.button("Calculate Annual Leave", type="primary", key="annual_leave_calculate_btn"):
        st.session_state.leave_calculator_state["result"] = calculate_leave()

    if st.session_state.leave_calculator_state["result"]:
        result = st.session_state.leave_calculator_state["result"]
        st.subheader("Calculation Results")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Base Leave", f"{result['base_leave']} days")
            st.metric("Service Bonus", f"+{result['service_bonus']} days")
        with col2:
            st.metric("Total Leave", f"{result['total_leave']} days", delta=f"({result['total_leave'] / result['leave_cap'] * 100:.1f}% of max)")
        
        st.progress(result['total_leave'] / result['leave_cap'], text="Progress towards maximum leave")

    st.subheader("Annual Leave Policy Reference")
    st.markdown("""
    | Job Category | Base Leave | Service Bonus | Maximum Leave |
    |-------------|------------|---------------|----------------|
    | General Staffs/Supervisors | 10 | +2 at 2yrs, +3 at 5yrs | 15 |
    | Assistant Managers | 12 | +2 at 2yrs, +3 at 5yrs | 17 |
    | Managers (incl. Senior Boutique) | 15 | +2 at 2yrs, +3 at 5yrs | 20 |
    | Sr. Flagship/Area Managers | 16 | +2 at 2yrs, +1 at 5yrs | 21 |
    | Directors and above | 20 | +2 at 2yrs, +1 at 5yrs | 23 |
    """, unsafe_allow_html=True)

# ===== 清除会话功能 =====
with st.sidebar:
    if st.button("🔄 Clear Conversation & Calculator"):
        st.session_state.messages = [{"role": "assistant", "content": "Bonjour! How can I help you today?"}]
        st.session_state.leave_calculator_state = {
            "job_category": "",
            "years_service": 0,
            "result": None
        }
        st.session_state.show_leave_calculator = False
        st.session_state.doc_references = {}
        if api_key and app_id:
            st.session_state.chatbot = ChatBot(api_key, app_id)
        st.rerun()

    st.divider()
    st.caption("© 2025 Dior HR Assistant")
