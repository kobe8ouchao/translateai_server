'''
Descripttion: 
Author: ouchao
Email: ouchao@sendpalm.com
version: 1.0
Date: 2024-06-13 16:28:38
LastEditors: ouchao
LastEditTime: 2025-03-14 10:23:30
'''
import os

from langchain.llms import OpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY', '')


os.environ["ARK_API_KEY"] = os.getenv('ARK_API_KEY', '')
os.environ["VOLC_ACCESSKEY"] = os.getenv('VOLC_ACCESSKEY', '')
os.environ["VOLC_SECRETKEY"] = os.getenv('VOLC_SECRETKEY', '')
from langchain_community.callbacks.manager import get_openai_callback
from langchain_openai import ChatOpenAI
import os
import json
import re
from doc import create_translation_chain_by_dk

def translate_text(text, source_lang, target_lang):
    # 创建 LLM
    llm = OpenAI(temperature=0.7)

    # 创建翻译提示模板
    template = """
    将以下{source_lang}文本翻译成{target_lang}：

    {text}

    翻译：
    """

    prompt = PromptTemplate(
        input_variables=["text", "source_lang", "target_lang"],
        template=template
    )

    # 创建翻译链
    chain = LLMChain(llm=llm, prompt=prompt)

    # 执行翻译
    result = chain.run(text=text, source_lang=source_lang, target_lang=target_lang)

    return result.strip()



def count_tokens_accurate(text,llm,lang):
    
    with get_openai_callback() as cb:
        try:
            # 只调用 LLM 来获取 token 计数，不实际执行翻译
            prompt = f"Text: {text}\nLanguage: {lang}"
            llm.predict(
                prompt
            )
            return cb.total_tokens
        except Exception as e:
            print(f"计算token时出错: {e}")
            # 如果出错，回退到估算方法
            return len(text) // 4



# 处理txt文件的翻译
def replace_text_in_txt(task_id, input_txt_path, output_txt_path, update_progress,lang,user_id=None):
    try:
        # 读取原始文本文件
        with open(input_txt_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # 按段落分割文本
        paragraphs = content.split('\n\n')
        total_paragraphs = len(paragraphs)
        translated_paragraphs = []
        
        # 创建翻译链
        translation_chain = create_translation_chain_by_dk(lang)
        # 用于计算token的变量
        total_tokens = 0
        # 逐段翻译
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                try:
                    # 翻译段落
                    translated = translation_chain.run(text=paragraph.strip(), lang=lang)
                    translated_paragraphs.append(translated)
                    print(f"原文: {paragraph.strip()}=========译文: {translated}")
                    # 计算并累加token
                    input_tokens = count_tokens_accurate(paragraph.strip(),translation_chain,lang)
                    output_tokens = count_tokens_accurate(translated,translation_chain,lang)
                    total_tokens += input_tokens + output_tokens
                    print(f"Token number =========: {input_tokens + output_tokens}")
                except Exception as e:
                    print(f"翻译段落时出错: {e}")
                    # 如果翻译失败，保留原文
                    translated_paragraphs.append(paragraph)
            else:
                # 保留空行
                translated_paragraphs.append('')
            
            # 更新进度
            progress = ((i + 1) / total_paragraphs) * 100
            update_progress(task_id, progress)
        
        # 将翻译后的段落写入新文件
        with open(output_txt_path, 'w', encoding='utf-8') as file:
            file.write('\n\n'.join(translated_paragraphs))
         # 更新用户tokens
        if user_id:
            try:
                from db.schema import User
                from bson import ObjectId
                user = User.objects(id=ObjectId(user_id)).first()
                if user:
                    # 确保tokens字段存在
                    if not hasattr(user, 'tokens') or user.tokens is None:
                        user.tokens = 5000
                    
                    # 减去使用的tokens
                    user.tokens -= total_tokens
                    if user.tokens < 0:
                        user.tokens = 0
                    
                    user.save()
                    print(f"用户 {user_id} 的tokens余额更新为: {user.tokens}，本次消耗: {total_tokens}")
            except Exception as e:
                print(f"更新用户token使用量时出错: {e}")
        update_progress(task_id, 100)
        return True
    except Exception as e:
        print(f"处理txt文件时出错: {e}")
        update_progress(task_id, 0)
        return False

# 处理JSON文件的翻译
def replace_text_in_json(task_id, input_json_path, output_json_path, update_progress,lang, user_id=None):
    try:
        # 读取原始JSON文件
        with open(input_json_path, 'r', encoding='utf-8') as file:
            content = json.load(file)
        
        # 创建翻译链
        translation_chain = create_translation_chain_by_dk(lang)
        
        # 计算总项数（用于进度计算）
        total_items = count_json_items(content)
        translated_items = [0]  # 使用列表以便在递归函数中修改
        # 用于计算token的变量
        total_tokens = [0]  # 使用列表以便在递归函数中修改
        # 递归翻译JSON对象
        translated_content = translate_json_object(content, translation_chain, lang, task_id, total_items, translated_items, 
                                                   update_progress,total_tokens)
        
        # 将翻译后的JSON写入新文件
        with open(output_json_path, 'w', encoding='utf-8') as file:
            json.dump(translated_content, file, ensure_ascii=False, indent=2)
        # 更新用户tokens
        if user_id:
            try:
                from db.schema import User
                from bson import ObjectId
                user = User.objects(id=ObjectId(user_id)).first()
                if user:
                    # 确保tokens字段存在
                    if not hasattr(user, 'tokens') or user.tokens is None:
                        user.tokens = 5000
                    
                    # 减去使用的tokens
                    user.tokens -= total_tokens[0]
                    if user.tokens < 0:
                        user.tokens = 0
                    
                    user.save()
                    print(f"用户 {user_id} 的tokens余额更新为: {user.tokens}，本次消耗: {total_tokens[0]}")
            except Exception as e:
                print(f"更新用户token使用量时出错: {e}")
                
        update_progress(task_id, 100)
        return True
    except Exception as e:
        print(f"处理JSON文件时出错: {e}")
        update_progress(task_id, 0)
        return False

# 计算JSON中的项数
def count_json_items(obj):
    count = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            count += 1  # 计算键
            count += count_json_items(value)  # 递归计算值
    elif isinstance(obj, list):
        for item in obj:
            count += count_json_items(item)
    elif isinstance(obj, str) and obj.strip():
        count += 1
    return count

# 递归翻译JSON对象
def translate_json_object(obj, translation_chain, lang, task_id, total_items, translated_items, update_progress,total_tokens):
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # 翻译键（如果是字符串）
            translated_key = key
            if isinstance(key, str) and key.strip():
                try:
                    translated_key = translation_chain.run(text=key.strip(), lang=lang).strip()
                    translated_items[0] += 1
                    print(f"原文: {key.strip()}=========译文: {translated_key}")
                    input_tokens = count_tokens_accurate(key.strip(),translation_chain,lang)
                    output_tokens = count_tokens_accurate(translated_key,translation_chain,lang)
                    total_tokens[0] += input_tokens + output_tokens
                    print(f"Token number =========: {input_tokens + output_tokens}")
                    update_progress(task_id, (translated_items[0] / total_items) * 100)
                except Exception as e:
                    print(f"翻译JSON键时出错: {e}")
            
            # 递归翻译值
            translated_value = translate_json_object(value, translation_chain, lang, task_id, total_items, translated_items, update_progress,total_tokens)
            result[translated_key] = translated_value
        return result
    elif isinstance(obj, list):
        return [translate_json_object(item, translation_chain, lang, task_id, total_items, translated_items, update_progress,total_tokens) for item in obj]
    elif isinstance(obj, str) and obj.strip():
        try:
            translated = translation_chain.run(text=obj.strip(), lang=lang).strip()
            translated_items[0] += 1
            print(f"原文: {obj.strip()}=========译文: {translated}")
            # 计算并累加token
            input_tokens = count_tokens_accurate(obj.strip(),translation_chain,lang)
            output_tokens = count_tokens_accurate(translated,translation_chain,lang)
            total_tokens[0] += input_tokens + output_tokens
            print(f"Token number =========: {input_tokens + output_tokens}")
            
            update_progress(task_id, (translated_items[0] / total_items) * 100)
            return translated
        except Exception as e:
            print(f"翻译JSON值时出错: {e}")
            return obj
    else:
        return obj

# 处理Markdown文件的翻译
def replace_text_in_markdown(task_id, input_md_path, output_md_path, update_progress,lang,user_id=None):
    try:
        # 读取原始Markdown文件
        with open(input_md_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # 分割Markdown内容
        # 保留代码块、标题、列表等结构
        # 用于计算token的变量
        total_tokens = 0
        # 定义正则表达式匹配模式
        code_block_pattern = r'```[\s\S]*?```'  # 代码块
        inline_code_pattern = r'`[^`]+`'  # 内联代码
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'  # 链接
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'  # 图片
        heading_pattern = r'^#+\s+.*$'  # 标题行
        
        # 提取所有需要保留原样的部分
        code_blocks = re.findall(code_block_pattern, content)
        inline_codes = re.findall(inline_code_pattern, content)
        links = re.findall(link_pattern, content)
        images = re.findall(image_pattern, content)
        
        # 替换所有需要保留的部分为占位符
        placeholder_map = {}
        
        for i, block in enumerate(code_blocks):
            placeholder = f"CODE_BLOCK_{i}"
            content = content.replace(block, placeholder)
            placeholder_map[placeholder] = block
        
        for i, code in enumerate(inline_codes):
            placeholder = f"INLINE_CODE_{i}"
            content = content.replace(code, placeholder)
            placeholder_map[placeholder] = code
        
        for i, link in enumerate(links):
            link_text, link_url = link
            original = f"[{link_text}]({link_url})"
            placeholder = f"LINK_{i}"
            content = content.replace(original, placeholder)
            placeholder_map[placeholder] = original
        
        for i, image in enumerate(images):
            alt_text, image_url = image
            original = f"![{alt_text}]({image_url})"
            placeholder = f"IMAGE_{i}"
            content = content.replace(original, placeholder)
            placeholder_map[placeholder] = original
        
        # 保留原始换行符，将内容按行分割而不是按段落
        lines = content.split('\n')
        total_lines = len(lines)
        translated_lines = []
        
        # 创建翻译链
        translation_chain = create_translation_chain_by_dk(lang)
        
        # 逐行翻译，但保持空行和格式行不变
        current_paragraph = []
        i = 0
        
        while i < total_lines:
            line = lines[i]
            
            # 检查是否是需要保留的行（空行、占位符行、标题行、列表项等）
            is_special_line = (
                not line.strip() or  # 空行
                any(placeholder in line for placeholder in placeholder_map.keys()) or  # 占位符
                re.match(r'^#+\s+', line) or  # 标题
                re.match(r'^[-*+]\s+', line) or  # 无序列表
                re.match(r'^\d+\.\s+', line) or  # 有序列表
                re.match(r'^>\s+', line) or  # 引用
                re.match(r'^(\s{2,}|\t)[-*+]\s+', line) or  # 缩进列表
                re.match(r'^(\s{2,}|\t)\d+\.\s+', line) or  # 缩进有序列表
                re.match(r'^(\s{4,}|\t+)', line) or  # 代码缩进
                re.match(r'^[=-]{3,}$', line) or  # 分隔线
                line.startswith('|') or  # 表格行
                line.startswith('---')  # 前置元数据
            )
            
            if is_special_line:
                # 如果当前有积累的段落，先翻译它
                if current_paragraph:
                    paragraph_text = '\n'.join(current_paragraph)
                    try:
                        translated_text = translation_chain.run(text=paragraph_text, lang=lang)
                        translated_lines.extend(translated_text.split('\n'))
                        print(f"原文: {paragraph_text}=========译文: {translated_text}")
                         # 计算并累加token
                        input_tokens = count_tokens_accurate(paragraph_text,translation_chain,lang)
                        output_tokens = count_tokens_accurate(translated_text,translation_chain,lang)
                        total_tokens += input_tokens + output_tokens
                        print(f"Token number =========: {input_tokens + output_tokens}")
                    except Exception as e:
                        print(f"翻译段落时出错: {e}")
                        translated_lines.extend(current_paragraph)  # 保留原文
                    current_paragraph = []
                
                # 保留特殊行原样
                translated_lines.append(line)
            else:
                # 收集普通文本行到当前段落
                current_paragraph.append(line)
            
            i += 1
            # 更新进度
            progress = (i / total_lines) * 100
            update_progress(task_id, progress)
        
        # 处理最后可能剩余的段落
        if current_paragraph:
            paragraph_text = '\n'.join(current_paragraph)
            try:
                translated_text = translation_chain.run(text=paragraph_text, lang=lang)
                translated_lines.extend(translated_text.split('\n'))
                print(f"原文: {paragraph_text}=========译文: {translated_text}")
                # 计算并累加token
                input_tokens = count_tokens_accurate(paragraph_text,translation_chain,lang)
                output_tokens = count_tokens_accurate(translated_text,translation_chain,lang)
                total_tokens += input_tokens + output_tokens
                print(f"Token number =========: {input_tokens + output_tokens}")
            except Exception as e:
                print(f"翻译段落时出错: {e}")
                translated_lines.extend(current_paragraph)  # 保留原文
        
        # 合并翻译后的行，保持原始换行
        translated_content = '\n'.join(translated_lines)
        
        # 恢复所有占位符
        for placeholder, original in placeholder_map.items():
            translated_content = translated_content.replace(placeholder, original)
        
        # 将翻译后的内容写入新文件
        with open(output_md_path, 'w', encoding='utf-8') as file:
            file.write(translated_content)
        # 更新用户tokens
        if user_id:
            try:
                from db.schema import User
                from bson import ObjectId
                user = User.objects(id=ObjectId(user_id)).first()
                if user:
                    # 确保tokens字段存在
                    if not hasattr(user, 'tokens') or user.tokens is None:
                        user.tokens = 5000
                    
                    # 减去使用的tokens
                    user.tokens -= total_tokens
                    if user.tokens < 0:
                        user.tokens = 0
                    
                    user.save()
                    print(f"用户 {user_id} 的tokens余额更新为: {user.tokens}，本次消耗: {total_tokens}")
            except Exception as e:
                print(f"更新用户token使用量时出错: {e}")
        update_progress(task_id, 100)
        return True
    except Exception as e:
        print(f"处理Markdown文件时出错: {e}")
        update_progress(task_id, 0)
        return False
