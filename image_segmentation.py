"""
图像分割模块 - 基于FastSAM的医学图像分割功能
"""
import os
import torch
import numpy as np
from PIL import Image
import cv2
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from fastsam import FastSAM, FastSAMPrompt
import tempfile
import uuid
from pathlib import Path


class ImageSegmentationService:
    """图像分割服务类"""

    def __init__(self, model_path="./weights/FastSAM_X.pt"):
        """
        初始化图像分割服务
        Args:
            model_path: FastSAM模型权重文件路径
        """
        self.model_path = model_path
        self.model = None
        self.device = torch.device(
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )

        # 创建必要的目录
        os.makedirs("./weights", exist_ok=True)
        os.makedirs("./static/uploads", exist_ok=True)
        os.makedirs("./static/segmented", exist_ok=True)

        self._load_model()

    def _load_model(self):
        """加载FastSAM模型"""
        try:
            if not os.path.exists(self.model_path):
                print(f"模型文件不存在: {self.model_path}")
                print("请下载FastSAM模型权重文件到weights目录")
                return False

            self.model = FastSAM(self.model_path)
            print(f"FastSAM模型加载成功，使用设备: {self.device}")
            return True
        except Exception as e:
            print(f"加载FastSAM模型失败: {e}")
            return False

    def segment_image(self, image_path,
                      input_size=1024,
                      iou_threshold=0.7,
                      conf_threshold=0.25,
                      better_quality=False,
                      withContours=True,
                      use_retina=True,
                      mask_random_color=True,
                      text_prompt=None,
                      point_prompts=None,
                      point_labels=None,
                      box_prompts=None):
        """
        对图像进行分割
        
        Args:
            image_path: 输入图像路径
            input_size: 输入图像尺寸
            iou_threshold: IoU阈值
            conf_threshold: 置信度阈值
            better_quality: 是否使用更好的质量
            withContours: 是否绘制轮廓
            use_retina: 是否使用retina masks
            mask_random_color: 是否使用随机颜色
            text_prompt: 文本提示
            point_prompts: 点提示
            point_labels: 点标签
            box_prompts: 框提示
            
        Returns:
            tuple: (分割结果图像路径, 原始图像路径, 分割信息)
        """
        if not self.model:
            return None, None, "模型未加载"

        try:
            # 加载和预处理图像
            input_image = Image.open(image_path).convert("RGB")

            # 调整图像尺寸
            w, h = input_image.size
            scale = input_size / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            resized_image = input_image.resize((new_w, new_h))

            # 运行FastSAM模型
            results = self.model(
                resized_image,
                device=self.device,
                retina_masks=use_retina,
                iou=iou_threshold,
                conf=conf_threshold,
                imgsz=input_size,
            )

            # 使用FastSAMPrompt进行后处理
            prompt_process = FastSAMPrompt(resized_image, results, device=str(self.device))

            # 处理不同类型的提示
            if text_prompt:
                # 文本提示分割
                annotations = prompt_process.text_prompt(text_prompt)
            elif point_prompts and point_labels:
                # 点提示分割
                # 调整点坐标到缩放后的图像
                scaled_points = [[int(x * scale) for x in point] for point in point_prompts]
                annotations = prompt_process.point_prompt(scaled_points, point_labels)
            elif box_prompts:
                # 框提示分割
                # 调整框坐标到缩放后的图像
                scaled_boxes = [[int(coord * scale) for coord in box] for box in box_prompts]
                annotations = prompt_process.box_prompt(bboxes=scaled_boxes)
            else:
                # 默认全图分割
                annotations = prompt_process.everything_prompt()

            # 生成分割结果图像
            segmented_image_array = prompt_process.plot_to_result(
                annotations=annotations,
                mask_random_color=mask_random_color,
                better_quality=better_quality,
                retina=use_retina,
                withContours=withContours,
            )

            # 保存分割结果
            timestamp = str(uuid.uuid4())
            segmented_filename = f"segmented_{timestamp}.png"
            segmented_path = os.path.join("./static/segmented", segmented_filename)

            # 将numpy数组转换为PIL图像并保存
            if isinstance(segmented_image_array, np.ndarray):
                if segmented_image_array.dtype != np.uint8:
                    segmented_image_array = (segmented_image_array * 255).astype(np.uint8)
                segmented_pil = Image.fromarray(segmented_image_array)
                segmented_pil.save(segmented_path)
            else:
                # 如果是其他类型，尝试直接保存
                segmented_image_array.save(segmented_path)

            # 生成分割信息
            num_masks = len(annotations) if annotations is not None else 0
            segmentation_info = {
                "num_masks": num_masks,
                "input_size": input_size,
                "device": str(self.device),
                "iou_threshold": iou_threshold,
                "conf_threshold": conf_threshold,
                "original_size": (w, h),
                "processed_size": (new_w, new_h)
            }

            return segmented_path, image_path, segmentation_info

        except Exception as e:
            print(f"图像分割失败: {e}")
            return None, None, f"分割失败: {str(e)}"

    def save_uploaded_image(self, image_file):
        """
        保存上传的图像文件
        
        Args:
            image_file: 上传的图像文件对象
            
        Returns:
            str: 保存的图像文件路径
        """
        try:
            # 生成唯一文件名
            timestamp = str(uuid.uuid4())
            filename = f"upload_{timestamp}.png"
            filepath = os.path.join("./static/uploads", filename)

            # 保存文件
            image_file.save(filepath)

            return filepath

        except Exception as e:
            print(f"保存上传图像失败: {e}")
            return None

    def get_model_status(self):
        """
        获取模型状态
        
        Returns:
            dict: 模型状态信息
        """
        return {
            "model_loaded": self.model is not None,
            "model_path": self.model_path,
            "device": str(self.device),
            "model_exists": os.path.exists(self.model_path)
        }


# 全局图像分割服务实例
image_segmentation_service = ImageSegmentationService()


def download_fastsam_model():
    """下载FastSAM模型权重文件"""
    import urllib.request

    model_url = "https://github.com/CASIA-IVA-Lab/FastSAM/releases/download/v1.0.0/FastSAM_X.pt"
    model_path = "./weights/FastSAM_X.pt"

    if not os.path.exists(model_path):
        print("正在下载FastSAM模型权重文件...")
        try:
            urllib.request.urlretrieve(model_url, model_path)
            print("模型下载完成")
            return True
        except Exception as e:
            print(f"模型下载失败: {e}")
            return False
    return True


if __name__ == "__main__":
    # 测试代码
    service = ImageSegmentationService()
    print("图像分割服务状态:", service.get_model_status())
