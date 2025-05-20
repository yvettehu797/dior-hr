import streamlit as st
from dashscope import Application
from http import HTTPStatus
import os
import re
import sys
import json
import pandas as pd
from typing import Dict, Callable, List, Any
import time  # 新增：用于模拟流式延迟

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

# 聊天机器人类（优化流式输出逻辑）
class ChatBot:
    def __init__(self, api_key: str, app_id: str):
        self.api_key = api_key
        self.app_id = app_id
        self.messages = []

    def ask(self, message: str) -> Dict:
        if len(self.messages) >= 7:
            self.messages.pop(1)  # 保留首尾，移除中间对话（共保留5轮对话）
            self.messages.pop(1)
        self.messages.append({"role": "user", "content": message})
        
        # 初始化流式响应
        responses = Application.call(
            api_key=self.api_key,
            app_id=self.app_id,
            messages=self.messages,
            prompt=message,
            stream=True,
            incremental_output=True,
            temperature=temperature,  # 新增：传入温度参数
            top_p=top_p,
            max_tokens=max_tokens
        )
        
        full_rsp = ""
        doc_references = []
        for response in responses:
            if response.status_code != HTTPStatus.OK:
                print(f'request_id={response.request_id} code={response.status_code} message={response.message}')
            elif response.output.text is not None:
                try:
                    response_data = json.loads(response.output.text)
                    chunk = response_data.get("result", "")
                    refs = response_data.get("doc_references", [])
                    if isinstance(refs, str):
                        refs = json.loads(refs) if refs else []
                    full_rsp += chunk  # 逐段累加响应
                    doc_references = refs
                    yield chunk, doc_references  # 流式返回每段内容和引用
                except json.JSONDecodeError:
                    chunk = response.output.text
                    full_rsp += chunk
                    yield chunk, doc_references  # 流式返回原始文本
        
        # 处理最终响应（非流式部分）
        self.messages.append({"role": "assistant", "content": full_rsp, "doc_references": doc_references})
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

# 用户输入处理（优化流式更新逻辑）
if prompt := st.chat_input("Ask a question about HR policies..."):
    if api_key and app_id:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        
        # 流式输出容器
        with st.chat_message("assistant", avatar="🤖") as message_container:
            message_placeholder = st.empty()  # 创建空容器用于实时更新
            full_response = ""
            doc_references = []
            
            try:
                # 调用流式API并逐段处理
                chatbot = st.session_state.chatbot
                stream_generator = chatbot.ask(prompt)  # 获取流式生成器
                
                for chunk, refs in stream_generator:
                    full_response += chunk
                    doc_references = refs
                    
                    # 清理临时标记（如<ref>标签）
                    cleaned_chunk = re.sub(r'<ref>.*?</ref>', '', full_response)
                    
                    # 实时更新内容（添加加载提示符号）
                    message_placeholder.markdown(f"{cleaned_chunk}▌")
                    time.sleep(0.05)  # 控制流式速度（可根据网络调整）
                    st.rerun()  # 强制刷新页面显示最新内容
                
                # 处理最终响应
                hr_compliant_response = f"{cleaned_chunk}\n\n---\n*For further HR assistance, contact your local HR representative.*"
                message_placeholder.markdown(hr_compliant_response)
                
                # 记录完整响应和引用
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": hr_compliant_response,
                    "doc_references": doc_references
                })
                
                # 显示文档引用
                if doc_references:
                    show_references(doc_references)
                
            except Exception as e:
                message_placeholder.error(f"⚠️ Error: {str(e)}")
                st.session_state.messages.pop()  # 移除未完成的响应记录

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
        if "chatbot" in st.session_state:
            del st.session_state.chatbot  # 重新初始化时会自动创建新实例
        st.rerun()

    st.divider()
    st.caption("© 2025 Dior HR Assistant")
