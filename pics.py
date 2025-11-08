# from openai import OpenAI
# import base64

# client = OpenAI(api_key="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")

# def encode_image(image_path):
#     with open(image_path, "rb") as image_file:
#         return base64.b64encode(image_file.read()).decode('utf-8')

# base64_image = encode_image("./upload/weibo.jpg")

# response = client.chat.completions.create(
#   model="gpt-4o",
#   messages=[
#     {
#       "role": "user",
#       "content": [
#         {"type": "text", "text": "Translate text to Simple Chinese?"},
#         {
#           "type": "image_url",
#           "image_url": {
#             "url": f"data:image/jpeg;base64,{base64_image}"
#           },
#         },
#       ],
#     }
#   ],
#   max_tokens=300,
# )

# print(response.choices[0])
import cv2
import numpy as np

def remove_text_with_white(image_path, output_path):
    # 读取图像
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # 使用自适应阈值处理
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    
    # 进行形态学操作
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    dilate = cv2.dilate(morph, kernel, iterations=3)
    
    # 查找轮廓
    contours, _ = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 创建白色掩码
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = float(w) / h
        area = cv2.contourArea(contour)
        
        # 放宽文字区域筛选条件
        if 0.03 < aspect_ratio < 30 and 20 < area < 20000 and 5 < h < 100:
            # 在掩码上绘制矩形
            cv2.rectangle(mask, (x, y), (x+w, y+h), (255), -1)
    
    # 对掩码进行膨胀操作，以确保覆盖整个文字区域
    mask = cv2.dilate(mask, kernel, iterations=2)
    
    # 创建结果图像
    result = image.copy()
    
    # 用白色覆盖检测到的文字区域
    result[mask == 255] = [255, 255, 255]
    
    # 保存结果
    cv2.imwrite(output_path, result)

# 使用示例
input_image = './upload/weibo3.jpg'
output_image = './upload/out.jpg'
remove_text_with_white(input_image, output_image)