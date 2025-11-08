import os
from docx import Document
from langchain.llms import OpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

# 设置 OpenAI API 密钥
os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY', '')

# 创建翻译链
def create_translation_chain(lang):
    llm = OpenAI(temperature=0.7)
    template = """
    将以下文本翻译成{lang}：

    {text}

    翻译：
    """
    prompt = PromptTemplate(input_variables=["lang","text"], template=template)
    return LLMChain(llm=llm, prompt=prompt)

def create_translation_chain_by_dk(lang):
    template = """
    你是一个专业的翻译专家，翻译内容要求词义准确并且简单，字数保持和原来差不多，（数字部分，数学公式，特殊符号,Markdown的符号就不用翻译），不要输出多余内容
    将以下文本翻译成{lang}：
    {text} 
    """
    prompt = PromptTemplate(
        input_variables=["text", "lang"],
        template=template
    )
    # Initialize ChatOpenAI with GPT-4
    llm = ChatOpenAI(
        # openai_api_base=#"https://ark.cn-beijing.volces.com/api/v3",
        openai_api_key=os.getenv('OPENAI_API_KEY', ''),  # 从环境变量读取API key
        model_name="gpt-4o",
        temperature=0.3,
        callbacks=[]
    )
    # 创建翻译链
    chain = LLMChain(llm=llm, prompt=prompt, callbacks=[])
    
    return chain

# 计算总字数
def count_total_words(doc):
    total_words = 0
    for paragraph in doc.paragraphs:
        total_words += len(paragraph.text.split())
    for table in doc.tables:
        total_words += count_words_in_table(table)
    return total_words

# 计算表格中的字数
def count_words_in_table(table):
    total_words = 0
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                total_words += len(paragraph.text.split())
            for nested_table in cell.tables:
                total_words += count_words_in_table(nested_table)
    return total_words

# 翻译段落并保持格式
def translate_paragraph(paragraph, translation_chain,lang):
    if paragraph.text.strip():
        origin = paragraph.text
        # 翻译文本
        translated_text = translation_chain.run(text=paragraph.text,lang=lang).strip()
        
        # 存储原始格式
        runs = paragraph.runs
        paragraph.clear()

        # 重新创建运行并应用原始格式
        new_run = paragraph.add_run(translated_text)
        if runs:
            original_run = runs[0]
            new_run.font.name = original_run.font.name
            new_run.font.size = original_run.font.size
            new_run.font.bold = original_run.font.bold
            new_run.font.italic = original_run.font.italic
            if original_run.font.color.rgb:
                new_run.font.color.rgb = original_run.font.color.rgb
        
        print(f"Translated: '{origin}' to '{translated_text}'")
        return len(origin.split())
    return 0

# 处理表格
def process_table(table, translation_chain, progress_callback, task_id, total_words, translated_words,lang):
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                translated_count = translate_paragraph(paragraph, translation_chain,lang)
                translated_words[0] += translated_count
                progress = translated_words[0] / total_words * 100
                progress_callback(task_id, progress)
            for nested_table in cell.tables:
                process_table(nested_table, translation_chain, progress_callback, task_id, total_words, translated_words,lang)

# 替换文本并保持格式
def replace_text_in_word(task_id, input_docx_path, output_docx_path, progress_callback, lang, user_id=None):
    doc = Document(input_docx_path)
    translation_chain = create_translation_chain_by_dk(lang)

    total_words = count_total_words(doc)
    translated_words = [0]  # 使用列表以便在闭包中更新
    # 用于计算token的变量
    total_tokens = 0
    for paragraph in doc.paragraphs:
        translated_count = translate_paragraph(paragraph, translation_chain,lang)
        translated_words[0] += translated_count
        progress = translated_words[0] / total_words * 100
        progress_callback(task_id, progress)

    for table in doc.tables:
        process_table(table, translation_chain, progress_callback, task_id, total_words, translated_words,lang)

    doc.save(output_docx_path)
    progress_callback(task_id, 100)  # 完成时确保进度设置为100%

def main():
    input_docx_path = 'file/test2.docx'
    output_docx_path = 'output_translated.docx'
    
    def dummy_progress_callback(task_id, progress):
        print(f"Task {task_id} progress: {progress}%")
    
    replace_text_in_word("task1", input_docx_path, output_docx_path, dummy_progress_callback,"English")
    print(f"Word document saved as {output_docx_path} with translated text")

if __name__ == '__main__':
    main()
