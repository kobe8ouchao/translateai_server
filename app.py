import base64
import datetime
from io import BytesIO
import uuid
from flask import Flask, request, jsonify, send_from_directory, send_file
import os
import fitz  # PyMuPDF
import threading
import time
from langchain.llms import OpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from doc import create_translation_chain_by_dk, replace_text_in_word
from werkzeug.security import generate_password_hash,check_password_hash
from bson import ObjectId
from mongoengine import connect, disconnect, register_connection, get_connection
from db.schema import User,UserFile
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from flask import redirect, session, url_for
import json
import secrets
import requests
import qrcode
from urllib.parse import quote
from ai import count_tokens_accurate, replace_text_in_txt, replace_text_in_json, replace_text_in_markdown
from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay.aop.api.domain.AlipayTradeAppPayModel import AlipayTradeAppPayModel
from alipay.aop.api.request.AlipayTradeAppPayRequest import AlipayTradeAppPayRequest
from db.schema import Order
import time
from alipay.aop.api.util.SignatureUtils import verify_with_rsa
from supabase import create_client, Client
import mimetypes
import tempfile

# 添加支付宝配置
ALIPAY_APPID = os.getenv('ALIPAY_APPID', '你的支付宝APPID')
ALIPAY_PUBLIC_KEY_PATH = os.getenv('ALIPAY_PUBLIC_KEY_PATH', '/path/to/alipay_public_key.pem')
ALIPAY_PRIVATE_KEY_PATH = os.getenv('ALIPAY_PRIVATE_KEY_PATH', '/path/to/app_private_key.pem')
ALIPAY_NOTIFY_URL = os.getenv('ALIPAY_NOTIFY_URL', 'http://your.domain/api/alipay/notify')
ALIPAY_RETURN_URL = os.getenv('ALIPAY_RETURN_URL', 'http://your.domain/payment/result')

# Google OAuth配置
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')  # 需要替换为你的Google客户端ID
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')  # 需要替换为你的Google客户端密钥
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8998/auth/google/callback')  # 需要根据你的实际部署情况修改

# 微信登录配置
WECHAT_APP_ID = os.getenv('WECHAT_APP_ID', '')  # 替换为你的微信AppID
WECHAT_APP_SECRET = os.getenv('WECHAT_APP_SECRET', '')  # 替换为你的微信AppSecret
WECHAT_REDIRECT_URI = os.getenv('WECHAT_REDIRECT_URI', 'http://localhost:8998/auth/wechat/callback')  #
# 存储任务进度的全局字典
progress_dict = {}
import stripe
from db.schema import Order
import datetime

# Stripe配置
stripe.api_key = os.getenv('STRIPE_API_KEY', '')  # 替换为你的Stripe密钥


# 跨域
def after_request(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'x-requested-with,content-type'
    return resp

#kobe824ouchao_db_user
#BUqjCRI3jsFMzLfE
def create_app():
    # 修改MongoDB连接
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/translateai?authSource=admin')
    # 从URI中提取数据库名称
    import urllib.parse
    parsed_uri = urllib.parse.urlparse(mongo_uri)
    db_name = parsed_uri.path.strip('/') if parsed_uri.path else 'translateai'
    print(f"连接数据库: {db_name}")
    
    # 尝试连接MongoDB，最多重试5次
    max_retries = 5
    retry_count = 0
    connection_success = False
    
    while retry_count < max_retries and not connection_success:
        try:
            print(f"尝试连接MongoDB: {mongo_uri}, 尝试 #{retry_count+1}")
            # 断开任何现有连接
            disconnect()
            # 使用register_connection替代connect以便在应用程序中持久保持连接
            register_connection(alias='default', host=mongo_uri, connect=True)
            print("MongoDB连接成功")
            connection_success = True
        except Exception as e:
            retry_count += 1
            print(f"MongoDB连接失败: {str(e)}")
            if retry_count < max_retries:
                print(f"将在5秒后重试... ({retry_count}/{max_retries})")
                time.sleep(5)
            else:
                print("达到最大重试次数，无法连接MongoDB")
    
    app = Flask(__name__)
    UPLOAD_FOLDER = 'upload'
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    # 确保上传文件夹存在
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)  
    app.after_request(after_request)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', GOOGLE_CLIENT_SECRET)
    app.config['SUPABASE_URL'] = os.getenv('SUPABASE_URL', '')
    app.config['SUPABASE_KEY'] = os.getenv('SUPABASE_KEY', '')
    app.config['SUPABASE_BUCKET'] = os.getenv('SUPABASE_BUCKET', 'translateai')
    if app.config['SUPABASE_URL'] and app.config['SUPABASE_KEY']:
        app.config['SUPABASE'] = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])

    # init_custom_router(app)
    # app.config['SECRET_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjYwMjQ2ZjQwZjQwZA=='
    init_router(app)

    return app

def update_progress(task_id, progress):
    progress_dict[task_id] = progress

def get_file_extension(filename):
    return os.path.splitext(filename)[1].lower()

def check_file_type(filename):
    ext = get_file_extension(filename)
    if ext == '.pdf':
        return 'pdf'
    elif ext == '.txt':
        return 'txt'
    elif ext in ('.doc', '.docx'):
        return 'word'
    elif ext in ('.jpg', '.jpeg', '.png', '.gif'):
        return 'img'
    elif ext == '.json':
        return 'json'
    elif ext in ('.md', '.markdown'):
        return 'markdown'
    else:
        return 'error'

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

# 计算总字数
def count_total_words(input_pdf_path):
    total_words = 0
    doc = fitz.open(input_pdf_path)
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)["blocks"]
        for block in blocks:
            if block['type'] == 0:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"]
                        total_words += len(text.split())
    doc.close()
    return total_words

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

# 替换原位置的文本
def replace_text_in_pdf(task_id, input_pdf_path, output_pdf_path, lang, user_id=None):
    doc = fitz.open(input_pdf_path) 
    translation_chain = create_translation_chain_by_dk(lang)
    total_words = count_total_words(input_pdf_path)
    translated_words = 0
    total_tokens = 0
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
                            translated = translation_chain.run(text=line_text.strip(), lang=lang).strip()
                            input_tokens = count_tokens_accurate(line_text.strip(),translation_chain,lang)
                            output_tokens = count_tokens_accurate(translated.strip(),translation_chain,lang)
                            total_tokens = total_tokens + input_tokens+output_tokens
                            print(f"Token input number =========: {input_tokens}======output numbeer: {output_tokens}")
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
                                text_width = fitz.get_text_length(translated, fontsize=base_size)
                                adjusted_size = base_size
                                
                                if text_width > line_rect.width:
                                    # 缩小字体以适应宽度
                                    scale_factor = line_rect.width / text_width * 0.95
                                    adjusted_size = base_size * scale_factor
                                
                                # 更精确的垂直定位
                                # 计算原始文本的中心点
                                center_y = (line_rect.y0 + line_rect.y1) / 2
                                # 根据字体大小调整垂直位置，使文本垂直居中
                                y_pos = center_y + adjusted_size * 0.3  # 调整系数可以根据实际效果微调
                                
                                # 使用 TextWriter 插入文本
                                text_writer = fitz.TextWriter(new_page.rect)
                                
                                # 尝试使用选定的字体，如果失败则回退到默认字体
                                if font_path and os.path.exists(font_path):
                                    try:
                                        font = fitz.Font(fontfile=font_path)
                                        text_writer.append(
                                            pos=fitz.Point(line_rect.x0, y_pos),
                                            text=translated,
                                            font=font,
                                            fontsize=adjusted_size
                                        )
                                        text_writer.write_text(new_page, color=convert_color(base_color))
                                        print(f"使用字体 {os.path.basename(font_path)} 插入文本成功")
                                    except Exception as e:
                                        print(f"使用指定字体失败: {e}，回退到默认字体")
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
                                    print("使用默认字体插入文本成功")
                                
                                # 更新进度
                                progress = (translated_words / total_words) * 100
                                update_progress(task_id, progress)
                            
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
    if user_id:
        try:
            user = User.objects(id=ObjectId(user_id)).first()
            if user:
                # 确保tokens字段存在
                if not hasattr(user, 'tokens') or user.tokens is None:
                    user.tokens = 5000
                
                # 减去使用的tokens
                user.tokens -= total_tokens
                user.save()
                print(f"用户 {user_id} 的tokens余额更新为: {user.tokens}，本次消耗: {total_tokens}")
        except Exception as e:
            print(f"更新用户token使用量时出错: {e}")
    update_progress(task_id, 100)

def init_router(app: Flask):
    def supabase_client():
        return app.config.get('SUPABASE')

    def local_path_for_key(key: str):
        parts = key.split('/')
        if len(parts) >= 3:
            user_id = parts[1]
            filename = '/'.join(parts[2:])
            return os.path.join(app.config['UPLOAD_FOLDER'], user_id, filename)
        return os.path.join(app.config['UPLOAD_FOLDER'], key)

    def storage_upload(bucket, key, data, content_type=None):
        client = supabase_client()
        if not client:
            path = local_path_for_key(key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
            return True
        opts = {"upsert": "true"}
        if content_type:
            opts["contentType"] = content_type
        return client.storage.from_(bucket).upload(key, data, file_options=opts)

    def storage_download(bucket, key):
        client = supabase_client()
        if not client:
            path = local_path_for_key(key)
            if not os.path.exists(path):
                return None
            with open(path, 'rb') as f:
                return f.read()
        try:
            return client.storage.from_(bucket).download(key)
        except Exception:
            return None

    def storage_exists(bucket, key):
        client = supabase_client()
        if not client:
            path = local_path_for_key(key)
            return os.path.exists(path)
        return storage_download(bucket, key) is not None
    @app.route('/translate', methods=['POST'])
    def translate_file():
        data = request.get_json()
        print(data)
        filename = data['filename']
        lang = data['lang']
        userId = data['userId']
        task_id = filename  # 可以用更复杂的方式生成唯一ID
        bucket = app.config['SUPABASE_BUCKET']
        input_key = f"uploads/{userId}/{filename}"
        output_name = f"translated_{lang}_{filename}"
        output_key = f"translations/{userId}/{output_name}"
        tmp_dir = os.path.join(tempfile.gettempdir(), 'translateai', userId)
        os.makedirs(tmp_dir, exist_ok=True)
        input_file_path = os.path.join(tmp_dir, filename)
        output_file_path = os.path.join(tmp_dir, output_name)
        fileType = check_file_type(filename)
        progress_dict[task_id] = 0  # 初始化进度
        
        # 检查翻译后的文件是否已经存在
        if storage_exists(bucket, output_key):
            progress_dict[task_id] = 100  # 初始化进度
            return jsonify({'message': 'Translation already exists', 'task_id': task_id})

        if fileType == 'excel':
            return jsonify({'message': 'Excel translation not implemented', 'task_id': task_id})
        if fileType == 'error':
            return jsonify({'message': 'Unsupported file type', 'task_id': task_id}), 400
        data_bytes = storage_download(bucket, input_key)
        if not data_bytes:
            return jsonify({'message': 'Source file not found in storage', 'task_id': task_id}), 404
        with open(input_file_path, 'wb') as f:
            f.write(data_bytes)

        def run_and_upload():
            if fileType == 'pdf':
                replace_text_in_pdf(task_id, input_file_path, output_file_path, lang, userId)
            elif fileType == 'txt':
                replace_text_in_txt(task_id, input_file_path, output_file_path, update_progress, lang, userId)
            elif fileType == 'json':
                replace_text_in_json(task_id, input_file_path, output_file_path, update_progress, lang, userId)
            elif fileType == 'markdown':
                replace_text_in_markdown(task_id, input_file_path, output_file_path, update_progress, lang, userId)
            elif fileType == 'word':
                replace_text_in_word(task_id, input_file_path, output_file_path, update_progress, lang, userId)
            else:
                return
            ct, _ = mimetypes.guess_type(output_name)
            with open(output_file_path, 'rb') as of:
                storage_upload(bucket, output_key, of.read(), ct or 'application/octet-stream')
            try:
                os.remove(input_file_path)
                os.remove(output_file_path)
            except Exception:
                pass

        threading.Thread(target=run_and_upload).start()
        return jsonify({'message': 'Translation started', 'task_id': task_id})
        

    @app.route('/progress/<task_id>', methods=['GET'])
    def get_progress(task_id):
        progress = progress_dict.get(task_id, 0)
        return jsonify({'progress': progress})

    @app.route('/test', methods=['GET'])
    def test_endpoint():
        return jsonify({"message": "Hello, world!"})

    @app.route('/upload', methods=['POST'])
    def upload_file():
        userId = request.form.get('userId')
        lang = request.form.get('targetLang')
        size = request.form.get('size')
        type = request.form.get('type')
        md5Name = request.form.get('md5Name')
        print("form",request.form)
        if not userId:
            print("error:User is required")
            return jsonify({"error": "User is required"}), 400
        if not lang:
            print("error:Taget Language is required")
            return jsonify({"error": "Taget Language is required"}), 400
        if 'file' not in request.files:
            print("No file part in the request")
            return jsonify({"error": "No file part in the request"}), 400
        
        file = request.files['file']
        if file.filename == '':
            print("No file selected for uploading")
            return jsonify({"error": "No file selected for uploading"}), 400
        
        if file:
            bucket = app.config['SUPABASE_BUCKET']
            key = f"uploads/{userId}/{md5Name}"
            ct, _ = mimetypes.guess_type(file.filename)
            data = file.read()
            res = storage_upload(bucket, key, data, ct or 'application/octet-stream')
            if not res:
                return jsonify({"error": "Storage upload failed"}), 500
            current_user = User.objects(id=ObjectId(userId)).first()
            
            user_file = UserFile(
                user=current_user,
                filename=md5Name,
                origin_name=file.filename,
                file_path=key,
                lang=lang,
                file_type=type,
                size=size
            )
            try:
                user_file.save()
            except Exception as e:
                print(f"UserFile save error: {e}")
            return jsonify({"message": "File successfully uploaded", "file_path": key}), 200
        else:
            return jsonify({"error": "File upload failed"}), 500

    @app.route('/files/<userId>/<filename>', methods=['GET'])
    def get_file(userId,filename):
        if not userId:
            return jsonify({"error": "User ID is required"}), 400
        bucket = app.config['SUPABASE_BUCKET']
        if filename.startswith('translated_'):
            key = f"translations/{userId}/{filename}"
        else:
            key = f"uploads/{userId}/{filename}"
        data = storage_download(bucket, key)
        if not data:
            return jsonify({"error": "File not found"}), 404
        ct, _ = mimetypes.guess_type(filename)
        return send_file(BytesIO(data), download_name=filename, mimetype=ct or 'application/octet-stream')

    @app.route('/register', methods=['POST'])
    def register_user():
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not username or not email or not password:
            return jsonify({'error': 'Missing required fields'}), 400

        # 检查用户名是否已存在
        if User.objects(name=username).first():
            return jsonify({'error': 'Username already exists'}), 400

        # 检查邮箱是否已存在
        if User.objects(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400

        # 创建新用户
        try:
        # 使用已经注册的数据库连接
            with get_connection(alias='default'):
                # 检查用户名是否已存在
                if User.objects(name=username).first():
                    return jsonify({'error': 'Username already exists'}), 400

                # 检查邮箱是否已存在
                if User.objects(email=email).first():
                    return jsonify({'error': 'Email already exists'}), 400

                # 创建新用户
                hashed_password = generate_password_hash(password)
                new_user = User(name=username, email=email, password=hashed_password)
                new_user.save()

                # 返回用户信息（不包括密码）
                return jsonify({
                    'message': 'User registered successfully',
                    'user': {
                        'id': str(new_user.id),
                        'username': new_user.name,
                        'email': new_user.email,
                        'tokens': new_user.tokens if hasattr(new_user, 'tokens') and new_user.tokens is not None else 0,
                        'vip': new_user.vip if hasattr(new_user, 'vip') and new_user.vip is not None else 0
                    }
                }), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        

    @app.route('/login', methods=['POST'])
    def login_user():
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Missing required fields'}), 400
        user = User.objects(email=email).first()
        if user and check_password_hash(user.password, password):
            return jsonify({
                'message': 'Login successful',
                'user': {
                    'id': str(user.id),
                    'username': user.name,
                    'email': user.email,
                    "vip_expired_at": user.vip_expired_at.isoformat() if hasattr(user, 'vip_expired_at') and user.vip_expired_at else None,
                    'tokens': user.tokens if hasattr(user, 'tokens') and user.tokens is not None else 0,
                    'vip': user.vip if hasattr(user, 'vip') and user.vip is not None else 0
                }
            }), 200
        else:
            return jsonify({'error': 'Invalid username or password'}), 401
        
    @app.route('/user/files', methods=['POST'])
    def get_user_files():
        data = request.get_json()
        userId = data.get('userId')
        if not userId:
            return jsonify({"error": "User is required"}), 400
        
        user = User.objects(id=ObjectId(userId)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user_files = UserFile.objects(user=user).order_by('-upload_date')
        files_data = []
        for user_file in user_files:
            files_data.append({
                "name": user_file.filename,
                "origin_name": user_file.origin_name,
                "status": 'done',
                "url": user_file.filename,
                "uid": '-1',
                "file_type": user_file.file_type,
                "size": user_file.size,
                "lang": user_file.lang,
                "upload_date": user_file.upload_date,
                "updated_at": user_file.updated_at
            })
        
        # 将 User 对象转换为字典
        user_data = {
            "id": str(user.id),
            "username": user.name,
            "vip_expired_at": user.vip_expired_at.isoformat() if hasattr(user, 'vip_expired_at') and user.vip_expired_at else None,
            "email": user.email,
            "tokens": user.tokens if hasattr(user, 'tokens') and user.tokens is not None else 0,
            "vip": user.vip if hasattr(user, 'vip') and user.vip is not None else 0
        }
        print(user_data,files_data)
        return jsonify({"user": user_data, "files": files_data}), 200
    
    @app.route('/auth/google', methods=['GET'])
    def google_auth():
        # 生成随机state参数防止CSRF攻击
        state = secrets.token_hex(16)
        session['oauth_state'] = state
        
        # 构建Google OAuth授权URL
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account"
        }
        
        # 构建授权URL但不直接重定向
        redirect_url = f"{auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
        print("redirect_url",redirect_url)
        # 返回URL给前端，让前端自行打开新窗口
        return jsonify({"auth_url": redirect_url})
    
    @app.route('/auth/google/callback', methods=['GET'])
    def google_callback():
        # 获取授权码和state
        code = request.args.get('code')
        state = request.args.get('state')
        print(code,state)
        # 验证state防止CSRF攻击
        if state != session.get('oauth_state'):
            return jsonify({"error": "Invalid state parameter"}), 400
        
        # 使用授权码获取访问令牌
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        token_response = requests.post(token_url, data=token_data)
        if token_response.status_code != 200:
            return jsonify({"error": "Failed to obtain access token"}), 400
        
        token_json = token_response.json()
        id_token_jwt = token_json['id_token']
        
        try:
            # 验证ID令牌
            idinfo = id_token.verify_oauth2_token(
                id_token_jwt, 
                google_requests.Request(), 
                GOOGLE_CLIENT_ID
            )
            
            # 获取用户信息
            user_email = idinfo['email']
            user_name = idinfo.get('name', user_email.split('@')[0])
            
            # 检查用户是否已存在
            user = User.objects(email=user_email).first()
            
            if user:
                # 用户已存在，更新登录信息
                user.last_login = datetime.datetime.now()
                user.save()
            else:
                # 创建新用户
                # 生成随机密码（用户不需要知道，因为他们使用Google登录）
                random_password = secrets.token_hex(16)
                hashed_password = generate_password_hash(random_password)
                
                new_user = User(
                    name=user_name,
                    email=user_email,
                    password=hashed_password,
                    platform="google",
                    token=idinfo['sub']
                )
                new_user.save()
                user = new_user
            # 将User对象转换为字典
            user_data = {
                'id': str(user.id),
                'username': user.name,
                "vip_expired_at": user.vip_expired_at.isoformat() if hasattr(user, 'vip_expired_at') and user.vip_expired_at else None,
                'tokens': user.tokens if hasattr(user, 'tokens') and user.tokens is not None else 0,
                'vip': user.vip if hasattr(user, 'vip') and user.vip is not None else 0,
                'email': user.email
            }
             # 返回一个HTML页面，该页面会向父窗口发送消息
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>登录成功</title>
                <script>
                    // 将用户数据发送到父窗口
                    window.onload = function() {{
                        if (window.opener) {{
                            // 向父窗口发送消息
                            window.opener.postMessage({{
                                type: 'google-auth-success',
                                user: {json.dumps(user_data)}
                            }}, '*');
                            
                            // 显示成功消息
                            document.getElementById('message').textContent = '登录成功，窗口即将关闭...';
                            
                            // 2秒后自动关闭窗口
                            setTimeout(function() {{ window.close(); }}, 5000);
                        }} else {{
                            document.getElementById('message').textContent = '无法与父窗口通信';
                        }}
                    }};
                </script>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background-color: #f5f5f5;
                    }}
                    .container {{
                        text-align: center;
                        padding: 2rem;
                        background-color: white;
                        border-radius: 8px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    h2 {{
                        color: #333;
                        margin-bottom: 1rem;
                    }}
                    .spinner {{
                        border: 4px solid rgba(0, 0, 0, 0.1);
                        width: 36px;
                        height: 36px;
                        border-radius: 50%;
                        border-left-color: #09f;
                        animation: spin 1s linear infinite;
                        margin: 1rem auto;
                    }}
                    @keyframes spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2 id="message">登录成功，正在处理...</h2>
                    <div class="spinner"></div>
                </div>
            </body>
            </html>
            """
            
            return html_content
            
        except ValueError as e:
            # 无效的令牌
            return jsonify({"error": f"Invalid token: {str(e)}"}), 400
        # 在init_router函数中添加以下路由
        
    # 存储微信登录状态的字典
    wechat_login_state = {}
    
    @app.route('/auth/wechat/login', methods=['GET'])
    def wechat_login():
        """
        获取微信登录二维码
        """
        # 生成唯一的状态码，用于标识本次登录请求
        state = str(uuid.uuid4())
        wechat_login_state[state] = {
            'status': 'waiting',  # 等待扫码
            'created_at': datetime.datetime.now()
        }
        
        # 构建微信授权URL
        auth_url = f"https://open.weixin.qq.com/connect/qrconnect?appid={WECHAT_APP_ID}&redirect_uri={quote(WECHAT_REDIRECT_URI)}&response_type=code&scope=snsapi_login&state={state}#wechat_redirect"
        print(auth_url)
        # 生成二维码
        
        return jsonify({
            'auth_url':auth_url,
            'state': state
        })
    
    @app.route('/auth/wechat/check_status/<state>', methods=['GET'])
    def check_wechat_login_status(state):
        """
        检查微信登录状态
        """
        if state not in wechat_login_state:
            return jsonify({'status': 'error', 'message': '无效的状态码'}), 400
        
        login_info = wechat_login_state[state]
        
        # 如果登录成功，返回用户信息
        if login_info['status'] == 'success':
            user_data = login_info['user_data']
            # 清理状态信息
            del wechat_login_state[state]
            return jsonify({
                'status': 'success',
                'user': user_data
            })
        
        # 如果超过10分钟，认为登录失败
        if (datetime.datetime.now() - login_info['created_at']).total_seconds() > 600:
            del wechat_login_state[state]
            return jsonify({'status': 'expired', 'message': '登录已过期'}), 400
        
        return jsonify({'status': login_info['status']})
    
    @app.route('/auth/wechat/callback', methods=['GET'])
    def wechat_callback():
        """
        微信登录回调
        """
        code = request.args.get('code')
        state = request.args.get('state')
        
        if not code or not state:
            return jsonify({'error': '缺少必要参数'}), 400
        
        if state not in wechat_login_state:
            return jsonify({'error': '无效的状态码'}), 400
        
        # 获取access_token
        token_url = f"https://api.weixin.qq.com/sns/oauth2/access_token?appid={WECHAT_APP_ID}&secret={WECHAT_APP_SECRET}&code={code}&grant_type=authorization_code"
        token_response = requests.get(token_url)
        
        if token_response.status_code != 200:
            return jsonify({'error': '获取access_token失败'}), 400
        
        token_data = token_response.json()
        if 'errcode' in token_data:
            return jsonify({'error': f"微信API错误: {token_data['errmsg']}"}), 400
        
        access_token = token_data['access_token']
        openid = token_data['openid']
        
        # 获取用户信息
        user_info_url = f"https://api.weixin.qq.com/sns/userinfo?access_token={access_token}&openid={openid}"
        user_info_response = requests.get(user_info_url)
        
        if user_info_response.status_code != 200:
            return jsonify({'error': '获取用户信息失败'}), 400
        
        user_info = user_info_response.json()
        print("user_info",user_info)
        nickname = user_info.get('nickname', '')
        if 'errcode' in user_info:
            return jsonify({'error': f"微信API错误: {user_info['errmsg']}"}), 400
        if isinstance(nickname, str):
            nickname = nickname.encode('latin1').decode('utf-8')
        
        # 检查用户是否已存在
        user = User.objects(platform="wechat", token=openid).first()
        
        if user:
            # 用户已存在，更新登录信息
            user.last_login = datetime.datetime.now()
            user.save()
        else:
            # 创建新用户
            random_password = secrets.token_hex(16)
            hashed_password = generate_password_hash(random_password)
            
            new_user = User(
                name=nickname,
                email=f"{openid}@wechat.user",  # 微信没有提供邮箱，使用openid作为邮箱
                password=hashed_password,
                platform="wechat",
                token=openid
            )
            new_user.save()
            user = new_user
        
        # 更新登录状态
        user_data = {
            'id': str(user.id),
            'username': user.name,
            'email': user.email,
            "vip_expired_at": user.vip_expired_at.isoformat() if hasattr(user, 'vip_expired_at') and user.vip_expired_at else None,
            'tokens': user.tokens if hasattr(user, 'tokens') and user.tokens is not None else 0,
            'vip': user.vip if hasattr(user, 'vip') and user.vip is not None else 0,
        }
        print("wechat user",user_data)
        
        wechat_login_state[state] = {
            'status': 'success',
            'created_at': datetime.datetime.now(),
            'user_data': user_data
        }
        
        # 返回一个HTML页面，通知用户登录成功
        html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>登录成功</title>
                <script>
                    // 将用户数据发送到父窗口
                    window.onload = function() {{
                        if (window.opener) {{
                            // 向父窗口发送消息
                            window.opener.postMessage({{
                                type: 'wechat-auth-success',
                                user: {json.dumps(user_data)}
                            }}, '*');
                            
                            // 显示成功消息
                            document.getElementById('message').textContent = '登录成功，窗口即将关闭...';
                            
                            // 2秒后自动关闭窗口
                            setTimeout(function() {{ window.close(); }}, 5000);
                        }} else {{
                            document.getElementById('message').textContent = '无法与父窗口通信';
                        }}
                    }};
                </script>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background-color: #f5f5f5;
                    }}
                    .container {{
                        text-align: center;
                        padding: 2rem;
                        background-color: white;
                        border-radius: 8px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    h2 {{
                        color: #333;
                        margin-bottom: 1rem;
                    }}
                    .spinner {{
                        border: 4px solid rgba(0, 0, 0, 0.1);
                        width: 36px;
                        height: 36px;
                        border-radius: 50%;
                        border-left-color: #09f;
                        animation: spin 1s linear infinite;
                        margin: 1rem auto;
                    }}
                    @keyframes spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2 id="message">登录成功，正在处理...</h2>
                    <div class="spinner"></div>
                </div>
            </body>
            </html>
            """
        
        return html_content
    
    @app.route('/user/info', methods=['POST'])
    def get_user_info():
        """
        获取用户信息接口
        """
        data = request.get_json()
        user_id = data.get('userId')
        
        if not user_id:
            return jsonify({"error": "用户ID不能为空"}), 400
        
        try:
            user = User.objects(id=ObjectId(user_id)).first()
            if not user:
                return jsonify({"error": "用户不存在"}), 404
            
            user_data = {
                "id": str(user.id),
                "username": user.name,
                "email": user.email,
                "vip_expired_at": user.vip_expired_at.isoformat() if hasattr(user, 'vip_expired_at') and user.vip_expired_at else None,
                "tokens": user.tokens if hasattr(user, 'tokens') and user.tokens is not None else 0,
                "vip": user.vip if hasattr(user, 'vip') and user.vip is not None else 0,
                "platform": user.platform if hasattr(user, 'platform') else "email",
                "last_login": user.last_login.isoformat() if hasattr(user, 'last_login') and user.last_login else None
            }
            
            return jsonify({
                "code": 200,
                "message": "获取用户信息成功",
                "data": user_data
            })
            
        except Exception as e:
            return jsonify({
                "code": 500,
                "message": f"获取用户信息失败: {str(e)}",
                "data": None
            }), 500


    # 初始化支付宝客户端
    def init_alipay():
        # 创建AlipayClientConfig对象
        alipay_client_config = AlipayClientConfig()
        alipay_client_config.server_url = "https://openapi.alipay.com/gateway.do"
        alipay_client_config.app_id = ALIPAY_APPID
        
        # 设置应用私钥
        with open(ALIPAY_PRIVATE_KEY_PATH) as f:
            app_private_key_string = f.read()
        alipay_client_config.app_private_key = app_private_key_string
        
        # 设置支付宝公钥
        with open(ALIPAY_PUBLIC_KEY_PATH) as f:
            alipay_public_key_string = f.read()
        alipay_client_config.alipay_public_key = alipay_public_key_string
        
        # 设置签名类型
        alipay_client_config.sign_type = "RSA2"
        
        # 创建AlipayClient
        alipay = DefaultAlipayClient(alipay_client_config)
        return alipay

    @app.route('/create-alipay-order', methods=['POST'])
    def create_alipay_order():
        """
        创建支付宝订单
        """
        try:
            data = request.get_json()
            user_id = data.get('userId')
            order_type = data.get('type')  # consumption 或 subscription
            
            if not user_id or not order_type:
                return jsonify({"error": "参数不完整"}), 400
            
            # 验证用户
            user = User.objects(id=ObjectId(user_id)).first()
            if not user:
                return jsonify({"error": "用户不存在"}), 404
            
            # 设置订单金额
            amount = 9.99 if order_type == 'consumption' else 49.90
            
            # 生成订单号
            order_no = f"ORDER_{int(time.time())}_{user_id[-6:]}"
            
            # 创建订单记录
            order = Order(
                user=user,
                order_no=order_no,
                amount=amount,
                type=order_type,
                status='pending'
            )
            order.save()
            
            # 初始化支付宝客户端
            alipay = init_alipay()
            
            # 生成支付链接
            # 创建 AlipayTradeAppPayModel 并设置参数
            model = AlipayTradeAppPayModel()
            model.out_trade_no = order_no
            model.total_amount = str(amount)
            model.subject = f"{'消耗性充值' if order_type == 'consumption' else '月度订阅'} - {order_no}"
            model.product_code = "QUICK_MSECURITY_PAY"
            
            # 创建 AlipayTradeAppPayRequest 对象
            request_obj = AlipayTradeAppPayRequest()
            request_obj.notify_url = ALIPAY_NOTIFY_URL
            request_obj.return_url = ALIPAY_RETURN_URL
            request_obj.biz_model = model
            
            # 调用支付接口
            response = alipay.execute(request_obj)
            order_string = response.body
            
            # 生成完整的支付链接
            pay_url = f"https://openapi.alipay.com/gateway.do?{order_string}"
            
            return jsonify({
                "code": 200,
                "message": "订单创建成功",
                "data": {
                    "order_no": order_no,
                    "amount": amount,
                    "pay_url": pay_url
                }
            })
            
        except Exception as e:
            return jsonify({
                "code": 500,
                "message": f"创建订单失败: {str(e)}",
                "data": None
            }), 500

    @app.route('/alipay/notify', methods=['POST'])
    def alipay_notify():
        """
        支付宝异步通知处理
        """
        try:
            data = request.form.to_dict()
            alipay = init_alipay()
            
            # 验证签名
            # 注意：支付宝SDK的新版本验证签名方式与旧版本不同
            signature = data.pop("sign")
            sign_type = data.pop("sign_type", "RSA2")
            
            # 构建待验签的字符串
            # 在实际使用中，需要根据支付宝文档正确构建待验签字符串
            # 这里简化处理，实际生产环境中应该按照支付宝文档完整实现
            
            # 按字母序排序参数
            params = sorted([(k, v) for k, v in data.items()])
            message = "&".join(f"{k}={v}" for k, v in params)
            
            # 使用支付宝公钥验证签名
            with open(ALIPAY_PUBLIC_KEY_PATH) as f:
                alipay_public_key_string = f.read()
            
            success = verify_with_rsa(alipay_public_key_string, message, signature)
            
            if success and data["trade_status"] in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                # 更新订单状态
                order = Order.objects(order_no=data["out_trade_no"]).first()
                if order and order.status == "pending":
                    order.status = "paid"
                    order.paid_at = datetime.datetime.now()
                    order.trade_no = data["trade_no"]
                    order.save()
                    
                    # 更新用户额度
                    user = order.user
                    if order.type == "consumption":
                        user.tokens = (user.tokens or 0) + 5000  # 假设9.99获得5000 tokens
                    else:  # subscription
                        user.vip = True
                    user.save()
                    
                return "success"
            return "fail"
            
        except Exception as e:
            print(f"处理支付回调时出错: {str(e)}")
            return "fail"
        
    @app.route('/create-stripe-payment-intent', methods=['POST'])
    def create_stripe_payment_intent():
        try:
            data = request.get_json()
            user_id = data.get('userId')
            order_type = data.get('type')  # consumption 或 subscription
            print("create-stripe-payment-intent data",data)
            if not user_id or not order_type:
                return jsonify({"error": "参数不完整"}), 400
            
            # 验证用户
            user = User.objects(id=ObjectId(user_id)).first()
            if not user:
                return jsonify({"error": "用户不存在"}), 404
            
            # 设置订单金额（美元）
            amount = data.get('amount')
            
            # 生成订单号
            order_no = f"ORDER_{int(time.time())}_{user_id[-6:]}"
            
            # 创建订单记录
            order = Order(
                user=user,
                order_no=order_no,
                amount=amount,
                type=order_type,
                status='pending'
            )
            order.save()
            
            # 创建 Stripe PaymentIntent
            intent = stripe.PaymentIntent.create(
                amount=int(amount),  # Stripe使用最小货币单位（美分）
                currency='usd',
                metadata={
                    'order_no': order_no,
                    'user_id': str(user.id),
                    'order_type': order_type
                }
            )
            
            return jsonify({
                "code": 200,
                "message": "支付意向创建成功",
                "data": {
                    "clientSecret": intent.client_secret,
                    "order_no": order_no,
                    "amount": amount
                }
            })
            
        except stripe.error.StripeError as e:
            print(f"Stripe错误: {str(e)}")
            return jsonify({
                "code": 400,
                "message": f"Stripe错误: {str(e)}",
                "data": None
            }), 400
        except Exception as e:
            print(f"Stripe错误: {str(e)}")
            return jsonify({
                "code": 500,
                "message": f"创建支付意向失败: {str(e)}",
                "data": None
            }), 500

    @app.route('/stripe/webhook', methods=['POST'])
    def stripe_webhook():
        """
        处理 Stripe Webhook 回调
        """
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')
        endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET', '')  # 替换为你的Webhook密钥

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except ValueError as e:
            return jsonify({"error": "Invalid payload"}), 400
        except stripe.error.SignatureVerificationError as e:
            return jsonify({"error": "Invalid signature"}), 400

        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            
            # 更新订单状态
            order_no = payment_intent['metadata']['order_no']
            order = Order.objects(order_no=order_no).first()
            
            if order and order.status == "pending":
                order.status = "paid"
                order.paid_at = datetime.datetime.now()
                order.trade_no = payment_intent['id']
                order.save()
                
                # 更新用户额度
                user = order.user
                print("webhook user",user.tokens)
                if order.type == "consumption":
                    user.tokens = (user.tokens or 0) + 10000  # 假设9.99获得10000 tokens
                else:  # subscription
                    user.vip = True
                    user.vip_expired_at = datetime.datetime.now() + datetime.timedelta(days=30)
                user.save()

        return jsonify({"received": True}), 200

