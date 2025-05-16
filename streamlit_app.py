import streamlit as st
from dashscope import Application
from http import HTTPStatus
import os
import re
import sys
from typing import Dict, Callable, List, Any

# 页面设置
st.set_page_config(page_title="Dior HR Assistant", page_icon=":robot:")
st.title("🤖 Dior HR Bot")
st.caption("Powered by Qwen Max through Alibaba Cloud Bailian Platform")

# ===== 配置区 =====
with st.sidebar:
    st.image("/workspaces/dior-test/images/截屏2025-05-09 17.19.08.png", width=150)
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

    # ===== 新增年假计算器模块 =====
    st.header("Annual Leave Calculator", divider="gray")
    
    job_category = st.selectbox(
        "Job Category",
        options=[
            "Retail and HO General Staffs & Supervisors",
            "Retail and HO Assistant Managers",
            "Retail and HO Managers (including Senior Boutique Managers)",
            "Sr. Flagship Boutique Manager/ Area Manager",
            "Associate Directors / Directors and above"
        ],
        key="leave_category"
    )

    years_service = st.number_input(
        "Years of Service",
        min_value=0,
        max_value=50,
        value=1,
        key="leave_years"
    )

    # 修正后的计算逻辑
    def calculate_leave(category, years):
        # 基础年假天数
        base_mapping = {
            "Retail and HO General Staffs & Supervisors": 10,
            "Retail and HO Assistant Managers": 12,
            "Retail and HO Managers (including Senior Boutique Managers)": 15,
            "Sr. Flagship Boutique Manager/ Area Manager": 16,
            "Associate Directors / Directors and above": 20
        }
        base = base_mapping.get(category, 0)
        
        # 服务年限奖金
        bonus = 0
        if years >= 2:
            bonus += 2
            if years >= 5:
                if category in ["Associate Directors / Directors and above", "Sr. Flagship Boutique Manager/ Area Manager"]:
                    bonus += 1  # 特定职位类别在5年时有额外1天
                else:
                    bonus += 3  # 其他职位类别在5年时有额外3天
        
        # 年假上限
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

    if st.button("Calculate Annual Leave", type="primary", use_container_width=True, key="leave_calculate"):
        result = calculate_leave(job_category, years_service)
        
        # 显示结果
        with st.expander("Calculation Results", expanded=True):
            st.write(f"Base Annual Leave: {result['base_leave']} days")
            st.write(f"Service Bonus: +{result['service_bonus']} days")
            st.write(f"Total Annual Leave: {result['total_leave']} days")
            st.write(f"(Maximum for this category: {result['leave_cap']} days)")
            
            # 视觉指示器
            percentage = (result['total_leave'] / result['leave_cap']) * 100
            st.progress(int(percentage))
            st.caption(f"You've reached {percentage:.1f}% of your category's maximum leave")

    # 政策参考表
    with st.expander("Annual Leave Policy Reference"):
        st.markdown("""
        | Job Category | Base Leave | Service Bonus | Maximum Leave |
        |-------------|------------|---------------|----------------|
        | General Staffs/Supervisors | 10 | +2 at 2yrs, +3 at 5yrs | 15 |
        | Assistant Managers | 12 | +2 at 2yrs, +3 at 5yrs | 17 |
        | Managers (incl. Senior Boutique) | 15 | +2 at 2yrs, +3 at 5yrs | 20 |
        | Sr. Flagship/Area Managers | 16 | +2 at 2yrs, +1 at 5yrs | 21 |
        | Directors and above | 20 | +2 at 2yrs, +1 at 5yrs | 23 |
        """)
    # ===== 年假计算器结束 =====

    st.divider()

# ===== 聊天区 =====
if not api_key or not app_id:
    st.warning("⚠️ Please provide App ID and API Key", icon="🔑")
    st.stop()

# 初始化聊天历史和文档引用
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": """
    Bonjour! Welcome to Dior HR Assistance.
    \nHow may I assist you today?
    """}]

if "doc_references" not in st.session_state:
    st.session_state.doc_references = {}

# 聊天机器人类 - 封装API调用逻辑
class ChatBot:
    def __init__(self, api_key: str, app_id: str):
        self.api_key = api_key
        self.app_id = app_id
        self.messages = []
        
    def ask(self, message: str, stream_callback: Callable[[str], None] = None) -> Dict:
        # 管理消息历史 - 保持对话长度适中
        if len(self.messages) >= 7:
            self.messages.pop(1)  # 移除旧消息
            self.messages.pop(1)

        # 添加新用户消息
        self.messages.append({"role": "user", "content": message})
        
        # 调用API
        responses = Application.call(
            api_key=self.api_key,
            app_id=self.app_id,
            messages=self.messages,
            prompt=message,
            stream=True,
            incremental_output=True
        )
        
        # 处理流式响应
        rsp = ''
        doc_references = []
        for response in responses:
            if response.status_code != HTTPStatus.OK:
                print(f'request_id={response.request_id}')
                print(f'code={response.status_code}')
                print(f'message={response.message}')
                print(f'请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code')
            elif response.output.text is not None:
                chunk = response.output.text
                if stream_callback:
                    stream_callback(chunk)
                print(chunk, end="", flush=True)
                sys.stdout.flush()
                rsp += chunk
                
        # 保存消息到历史
        self.messages.append({"role": "assistant", "content": rsp})
        
        # 提取文档引用（假设最后一个响应包含所有引用信息）
        if hasattr(response.output, 'doc_references') and response.output.doc_references is not None:
            for ref in response.output.doc_references:
                doc_references.append({ref.get("index_id"): ref.get("doc_name")})
        
        return {"full_rsp": rsp, "doc_references": doc_references}

# 初始化聊天机器人
if "chatbot" not in st.session_state:
    st.session_state.chatbot = ChatBot(api_key, app_id)

# 显示历史消息
for msg in st.session_state.messages:
    avatar = "🤖" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        
        # 如果是助手消息且有文档引用，显示引用和图片
        if msg["role"] == "assistant" and "doc_references" in msg and msg["doc_references"]:
            st.divider()
            st.subheader("📚 References")
            
            # 显示引用列表
            for i, reference in enumerate(msg["doc_references"]):
                for k, v in reference.items():
                    st.caption(f"Reference {k}: {v}")
            
            # 创建图片扩展区
            with st.expander("🖼️ View Related Images"):
                for reference in msg["doc_references"]:
                    for k, doc_name in reference.items():
                        image_path = f'images/{doc_name}.png'
                        
                        # 检查图片是否存在
                        if os.path.exists(image_path):
                            st.image(image_path, caption=f"{doc_name}", use_container_width=True)
                        else:
                            st.warning(f"Image not found: {image_path}")
                            # 可以添加默认图片或占位符
                            st.image("/workspaces/dior-test/images/截屏2025-05-09 17.19.08.png", caption="Placeholder Image", use_container_width=True)

# 用户输入处理
if prompt := st.chat_input("Ask your HR question..."):
    # 添加用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
    
    # 生成AI回复
    with st.chat_message("assistant", avatar="🤖"):
        message_placeholder = st.empty()
        resp_container = [""]  # Using a list to hold the response
        
        def stream_callback(chunk: str) -> None:
            resp_container[0] += chunk  # Accessing the list element
            message_placeholder.markdown(resp_container[0] + "▌")

        try:
            # 调用API
            response = st.session_state.chatbot.ask(prompt, stream_callback)
            
            # 处理响应
            full_response = response["full_rsp"]
            doc_references = response["doc_references"]
            
            # 保存文档引用
            if doc_references:
                st.session_state.doc_references[len(st.session_state.messages)] = doc_references
            
            # 后处理回复
            cleaned_response = re.sub(r'<ref>.*?</ref>', '', full_response)
            hr_compliant_response = f"{cleaned_response}\n\n---\n*For official policy documents, please refer to the Dior Employee Handbook or contact your HR*"
            
            # 更新UI - 先显示清理后的回复
            message_placeholder.markdown(hr_compliant_response)
            
            # 立即显示文档引用（如果有）
            if doc_references:
                st.divider()
                st.subheader("📚 References")
                
                # 显示引用列表
                for i, reference in enumerate(doc_references):
                    for k, v in reference.items():
                        st.caption(f"Reference {k}: {v}")
                
                # 创建图片扩展区
                with st.expander("🖼️ View Related Images"):
                    for reference in doc_references:
                        for k, doc_name in reference.items():
                            image_path = f'images/{doc_name}.png'
                            
                            # 检查图片是否存在
                            if os.path.exists(image_path):
                                st.image(image_path, caption=f"{doc_name}", use_container_width=True)
                            else:
                                st.warning(f"Image not found: {image_path}")
                                st.image("/workspaces/dior-test/images/截屏2025-05-09 17.19.08.png", caption="Placeholder Image", use_container_width=True)
            
            # 添加到会话历史
            st.session_state.messages.append({
                "role": "assistant",
                "content": hr_compliant_response,
                "doc_references": doc_references
            })
                
        except Exception as e:
            error_msg = f"⚠️ Service unavailable. Technical details: {str(e)}"
            message_placeholder.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Apologies, we're experiencing technical difficulties. Please contact your HR for immediate assistance."
            })


# ===== 功能区 =====
with st.sidebar:
    st.divider()
    if st.button("🔄 Restart Conversation"):
        st.session_state.messages = [{"role": "assistant", "content": "Welcome to Dior HR Assistance. What would you like to discuss today?"}]
        st.session_state.doc_references = {}
        st.session_state.chatbot = ChatBot(api_key, app_id)
        st.rerun()
    st.divider()
    st.caption("© 2025 Dior HR Assistant")

