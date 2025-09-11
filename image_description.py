"""
图像描述模块 - 医学图像描述功能（改用阿里云通义千问 Qwen-VL）
"""
import base64
import os
import requests
import time
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class ImageDescriptionService:
    """图像描述服务类（通义千问 Qwen-VL 版本）"""
    def __init__(self):
        """
        初始化图像描述服务，使用阿里云通义千问多模态模型
        """
        self.api_key = os.getenv("ALI_API_KEY")
        self.base_url = os.getenv("ALI_BASE_URL")
        if not self.api_key:
            raise EnvironmentError("请在 .env 中设置 ALI_API_KEY")
        if not self.api_key:
            raise EnvironmentError("请在 .env 中设置 ALI_API_KEY")
        self.model = os.getenv("ALI_MODEL1", "qwen-vl-plus")

    def encode_image_to_base64(self, image_path):
        """
        将图像文件编码为 base64 格式
        """
        try:
            with open(image_path, "rb") as f:
                b_image = f.read()
            return base64.b64encode(b_image).decode('utf-8')
        except Exception as e:
            print(f"图像编码失败: {e}")
            return None

    def describe_medical_image(self, segmented_image_path):
        """
        描述医学图像（仅处理分割后的图像）
        Args:
            segmented_image_path: 分割后图像路径
        Returns:
            tuple: (成功标志, 描述文本或错误信息)
        """
        try:
            # 检查图像是否存在
            if not segmented_image_path or not os.path.exists(segmented_image_path):
                return False, "分割后图像不存在"
            # 编码图像为 Base64
            image_b64 = self.encode_image_to_base64(segmented_image_path)
            if not image_b64:
                return False, "图像编码失败"
            return self._call_qwen_vl(image_b64, is_medical=True)

        except Exception as e:
            return False, f"图像描述生成失败: {str(e)}"

    def describe_single_image(self, image_path, custom_prompt=None):
        """
        描述单张图像（通用版）
        Args:
            image_path: 图像文件路径
            custom_prompt: 自定义提示词
        Returns:
            tuple: (成功标志, 描述文本或错误信息)
        """
        try:
            if not os.path.exists(image_path):
                return False, "图像文件不存在"
            image_b64 = self.encode_image_to_base64(image_path)
            if not image_b64:
                return False, "图像编码失败"
            return self._call_qwen_vl(image_b64, custom_prompt=custom_prompt, is_medical=False)
        except Exception as e:
            return False, f"图像描述生成失败: {str(e)}"

    def _call_qwen_vl(self, image_base64, custom_prompt=None, is_medical=True):
        """
        调用通义千问 VL 模型进行图像描述
        Args:
            image_base64: Base64 编码的图像数据
            custom_prompt: 自定义提示词
            is_medical: 是否为医学图像（决定使用医学专用提示词）
        Returns:
            tuple: (成功标志, 描述文本或错误信息)
        """
        try:
            # 构建提示词
            if is_medical:
                prompt = """
            请作为一名专业的医学影像专家，分析这张经过图像分割处理的医学影像。
            请从以下几个方面进行专业分析：
            1. 影像类型识别：判断这是什么类型的医学影像（如X光、CT、MRI、超声、病理切片等）
            2. 分割结果分析：识别图像分割后突出显示的主要解剖结构和区域
            3. 医学结构识别：识别图像中的重要医学结构和器官
            4. 异常发现：如果存在异常区域，请指出可能的病变或异常表现
            5. 临床意义：基于分割结果和影像表现，说明潜在的临床意义
            请用专业但易懂的语言进行描述，为医学诊断提供有价值的参考信息，
            注意最后的输出不要包含与结果无关的特殊字符。
                """
            else:
                prompt = custom_prompt or "请详细描述这张图像的内容和特征。"
            # 构建消息（Qwen-VL 多模态格式）
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
            # 请求头
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            # 请求体
            data = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3  # 降低温度，让回答更稳定专业
            }
            # 发送请求
            start_time = time.time()
            url = f"{self.base_url}/chat/completions"
            response = requests.post(url, headers=headers, json=data, timeout=60)

            end_time = time.time()
            print(f"通义千问 VL 请求耗时: {end_time - start_time:.2f} 秒")
            if response.status_code == 200:
                result = response.json()
                # print(f"原始响应: {result}")  # 调试用
                # 提取回复内容（OpenAI 兼容格式）
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0]['message']['content']
                    return True, content.strip()
                else:
                    return False, "响应格式异常，无法提取描述内容"

            else:
                error_msg = f"请求失败: {response.status_code} - {response.text}"
                print(error_msg)
                return False, error_msg

        except requests.exceptions.Timeout:
            return False, "请求超时，请稍后重试"
        except requests.exceptions.RequestException as e:
            return False, f"网络请求异常: {str(e)}"
        except Exception as e:
            return False, f"图像描述生成失败: {str(e)}"


# 全局图像描述服务实例
image_description_service = ImageDescriptionService()

if __name__ == "__main__":
    # 测试代码
    service = ImageDescriptionService()
    print("通义千问图像描述服务初始化完成")

    # 测试用例（请替换为你的本地图片路径）
    test_image_path = "肿瘤.jpg"  # ← 替换为你的测试图片路径
    if os.path.exists(test_image_path):
        print(f"\n正在测试医学图像描述: {test_image_path}")
        success, description = service.describe_medical_image(test_image_path)
        if success:
            print("\n描述结果:")
            print("=" * 80)
            print(description)
            print("=" * 80)
        else:
            print(f"\n失败: {description}")
    else:
        print(f"测试图片 {test_image_path} 不存在，请替换为有效路径")
