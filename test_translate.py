import fitz  # PyMuPDF
import os
from PIL import Image
import io
import tempfile
import requests
import shutil

from ai import count_tokens_accurate
from app import convert_color, replace_text_in_pdf
from doc import create_translation_chain_by_dk



def replace_text_in_pdf(task_id, input_pdf_path, output_pdf_path, lang):
    doc = fitz.open(input_pdf_path) 
    translation_chain = create_translation_chain_by_dk(lang)
    translated_words = 0
    
    # 根据目标语言选择合适的字体
    if lang.lower() in ["chinese", "zh", "cn", "中文"]:
        font_path = "./fonts/NotoSans-Regular.ttf"
        print(f"为中文选择字体: NotoSans-Regular.ttf")
    else:
        font_path = "./fonts/NotoSans-VariableFont.ttf"
        print(f"为{lang}选择字体: NotoSans-VariableFont.ttf")
    
    if not os.path.exists(font_path):
        print(f"警告: 找不到字体文件 {font_path}，将使用默认字体")
        font_path = None
    
    # 直接复制原始PDF并修改文本
    new_doc = fitz.open(input_pdf_path)
    
    for page_num in range(len(doc)):
        # 获取原始页面和新页面
        original_page = doc[page_num]
        new_page = new_doc[page_num]
        
        # 获取文本块
        text_blocks = original_page.get_text("dict")["blocks"]
        
        for block in text_blocks:
            if block['type'] == 0:  # 文本块
                for line in block["lines"]:
                    # 收集一行中的所有文本和对应的矩形区域
                    line_text = ""
                    line_spans = []
                    
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                            line_text += text + " "
                            line_spans.append({
                                "text": text,
                                "rect": fitz.Rect(span["bbox"]),
                                "size": span["size"],
                                "color": span["color"]
                            })
                    
                    # 如果这一行有文本，则进行翻译
                    if line_text.strip():
                        try:
                            # 翻译整行文本
                            print(count_tokens_accurate(line_text.strip()))
                            translated = translation_chain.run(text=line_text.strip(), lang=lang).strip()
                            print(f"原文: {line_text.strip()}=========译文: {translated}")
                            translated_words += len(line_text.split())
                            
                            # 计算整行的边界矩形
                            if line_spans:
                                first_span = line_spans[0]
                                last_span = line_spans[-1]
                                line_rect = fitz.Rect(
                                    first_span["rect"].x0,
                                    min(span["rect"].y0 for span in line_spans),
                                    last_span["rect"].x1,
                                    max(span["rect"].y1 for span in line_spans)
                                )
                                
                                # 清除整行区域
                                pixmap = original_page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=line_rect)
                                bg_color = pixmap.pixel(0, 0)
                                bg_color = tuple(c/255 for c in bg_color[:3])
                                new_page.draw_rect(line_rect, color=None, fill=bg_color)
                                
                                # 使用第一个span的字体大小和颜色作为基准
                                base_size = first_span["size"]
                                base_color = first_span["color"]
                                
                                # 计算文本宽度和适当的字体大小
                                if font_path:
                                    try:
                                        # 使用指定字体计算文本宽度
                                        font = fitz.Font(fontfile=font_path)
                                        text_width = font.text_length(translated, fontsize=base_size)
                                    except Exception as e:
                                        print(f"加载字体失败: {e}，使用默认方法计算文本宽度")
                                        text_width = fitz.get_text_length(translated, fontsize=base_size)
                                else:
                                    text_width = fitz.get_text_length(translated, fontsize=base_size)
                                
                                adjusted_size = base_size
                                
                                if text_width > line_rect.width:
                                    # 缩小字体以适应宽度
                                    scale_factor = line_rect.width / text_width * 0.95
                                    adjusted_size = base_size * scale_factor
                                
                                # 更精确的垂直定位
                                center_y = (line_rect.y0 + line_rect.y1) / 2
                                y_pos = center_y + adjusted_size * 0.3
                                
                                # 使用 TextWriter 插入文本
                                text_writer = fitz.TextWriter(new_page.rect)
                                
                                # 根据是否有字体文件决定使用哪种方式插入文本
                                if font_path:
                                    try:
                                        font = fitz.Font(fontfile=font_path)
                                        text_writer.append(
                                            pos=fitz.Point(line_rect.x0, y_pos),
                                            text=translated,
                                            font=font,
                                            fontsize=adjusted_size
                                        )
                                        text_writer.write_text(new_page, color=convert_color(base_color))
                                        print(f"使用指定字体插入整行文本成功")
                                    except Exception as e:
                                        print(f"使用指定字体失败: {e}，尝试使用默认字体")
                                        # 回退到默认字体
                                        text_writer.append(
                                            pos=fitz.Point(line_rect.x0, y_pos),
                                            text=translated,
                                            fontsize=adjusted_size
                                        )
                                        text_writer.write_text(new_page, color=convert_color(base_color))
                                else:
                                    # 使用默认字体
                                    text_writer.append(
                                        pos=fitz.Point(line_rect.x0, y_pos),
                                        text=translated,
                                        fontsize=adjusted_size
                                    )
                                    text_writer.write_text(new_page, color=convert_color(base_color))
                                    print(f"使用默认字体插入整行文本成功")
                                
                        except Exception as e:
                            print(f"处理整行文本时出错: {e}")
                            # 如果整行处理失败，回退到逐个span处理
                            for span in line["spans"]:
                                # 这里可以放原来的span处理代码作为备用
                                pass
   
    
    # 保存文档时使用优化选项
    new_doc.save(
        output_pdf_path,
        garbage=4,  # 最大程度清理
        deflate=True,  # 使用压缩
        clean=True,  # 清理未使用对象
        pretty=False  # 不美化输出以减小文件大小
    )
    new_doc.close()

# 使用示例
if __name__ == "__main__":
    input_pdf = "test_files/test2.pdf"
    output_pdf = "test_files/output_translated.pdf"
    target_language = "Chinese"
    replace_text_in_pdf("",input_pdf, output_pdf, target_language)