'''
Descripttion: 
Author: ouchao
Email: ouchao@sendpalm.com
version: 1.0
Date: 2024-06-13 16:39:12
LastEditors: ouchao
LastEditTime: 2025-02-26 16:48:22
'''
import fitz  # PyMuPDF
import os
from langchain.llms import OpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY', '')

# 转换颜色值
def convert_color(color):
    if isinstance(color, (tuple, list)) and len(color) == 3:
        return tuple(c / 255.0 for c in color)
    elif isinstance(color, int):
        r = (color >> 16) & 255
        g = (color >> 8) & 255
        b = color & 255
        return (r / 255.0, g / 255.0, b / 255.0)
    else:
        return (0, 0, 0)

# 创建翻译链
def create_translation_chain():
    llm = OpenAI(temperature=0.7)
    template = """
    将以下文本翻译成英文：

    {text}

    翻译：
    """
    prompt = PromptTemplate(input_variables=["text"], template=template)
    return LLMChain(llm=llm, prompt=prompt)

# 替换原位置的文本
def replace_text_in_pdf(input_pdf_path, output_pdf_path):
    doc = fitz.open(input_pdf_path)
    translation_chain = create_translation_chain()

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)["blocks"]
        for block in blocks:
            if block['type'] == 0:  # type 0 means text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        rect = fitz.Rect(span["bbox"])
                        text = span["text"]
                        if text.strip():  # 确保不是空白文本
                            # 获取原文本的左上角坐标和基线
                            origin = span["origin"]
                            
                            # 翻译文本
                            translated_text = translation_chain.run(text=text).strip()
                            
                            # 删除原文本
                            page.add_redact_annot(rect)
                            page.apply_redactions()
                            
                            # 插入翻译后的文本
                            font_size = span["size"]
                            color = convert_color(span["color"])
                            font = span["font"]  # 获取原文本的字体
                            
                            # 调试信息
                            print(f"Replacing text '{text}' with '{translated_text}'")
                            print(f"Font: {font}, Size: {font_size}, Color: {color}")
                            print(f"Origin: {origin}")
                            
                            try:
                                # 使用原文本的左上角坐标和字体信息插入新文本
                                page.insert_text(origin, translated_text,
                                                 fontname='helv',  # 使用原文本的字体
                                                 fontsize=font_size,
                                                 color=color)
                                print("Text inserted successfully")
                            except Exception as e:
                                print(f"Error inserting text: {e}")
    doc.save(output_pdf_path)
    doc.close()

# 主函数
def main():
    input_pdf_path = 'file/test.pdf'
    output_pdf_path = 'output_translated.pdf'
    
    # 在原位置替换文本
    replace_text_in_pdf(input_pdf_path, output_pdf_path)
    print(f"PDF saved as {output_pdf_path} with translated text")

if __name__ == '__main__':
    main()
