# 文件创建时间: 2025-05-22  
# 上次修改时间: 2025-05-23
import requests # 用于发送 HTTP 请求，与网站服务器交互
from bs4 import BeautifulSoup # 用于解析 HTML 内容，方便提取数据
import html2text # 用于将 HTML 内容转换为 Markdown 格式
import os # 用于处理文件和文件夹路径，例如创建文件夹、拼接路径
import re # 用于正则表达式操作，例如清洗文件名中的非法字符
import time # 用于控制请求频率，避免过快访问服务器
import json # 用于处理 JSON 数据，微信后台很多接口返回 JSON 格式
import html # 新增：用于 HTML 反转义
import concurrent.futures  # 添加到顶部导入区域
import argparse

# --- 用户配置区 ---
# !!! 重要 !!! 请务必仔细阅读注释并正确填写以下信息
# 1. COOKIE_STRING: 你的微信公众号后台 Cookie。
#    获取方法:
#    a. 使用 Chrome 或 Edge 浏览器登录你的微信公众号后台 (mp.weixin.qq.com)。
#    b. 导航到"发布" -> "已发表内容"页面。
#    c. 按 F12 打开浏览器开发者工具。
#    d. 切换到"网络(Network)"面板。
#    e. 刷新一下"已发表内容"页面，或者点击翻页。
#    f. 在网络请求列表中，找到一个以 "appmsg?action=list_ex" 开头的请求（或者类似的，用于加载文章列表的请求）。
#       点击这个请求。
#    g. 在右侧的详情面板中，找到"标头(Headers)"部分，向下滚动到"请求标头(Request Headers)"。
#    h. 找到名为 "Cookie:" 的条目，复制它后面跟着的【完整】字符串。
#    i. 将复制的 Cookie 字符串粘贴到下面的引号之间。
COOKIE_STRING = "很长的一串cookie"

# 2. TOKEN: 你的微信公众号 token。
#    获取方法:
#    登录微信公众号后台后，查看浏览器地址栏的 URL，通常会包含 "token=一串数字或字母" 这样的参数。
#    复制这串数字或字母，粘贴到下面的引号之间。
TOKEN = "1234567"

# 3. FAKEID (或 biz): 你的公众号的唯一标识符。
#    获取方法 (推荐 fakeid):
#    在上述获取 Cookie 的步骤 f 中，查看 "appmsg?action=list_ex..." 请求的 URL，
#    它通常会包含 "fakeid=一串纯数字" 这样的参数。复制这串数字。
#    或者，如果你知道公众号的 biz (通常以 Mz 开头，以 == 结尾)，也可以使用，但下方获取文章列表的 URL 模板可能需要调整。
#    !!! 注意：根据你提供的新 URL 格式，fakeid 可能不再需要。如果脚本运行正常，可以忽略此项。
FAKEID = "在此处粘贴你的 fakeid (一串数字)" # 此项暂不需要填写，暂时保留

# 4. TOTAL_ARTICLES_TO_FETCH: 你希望从最新开始导出的原创文章数量上限。
#    例如，输入 50 表示最多导出最近的 50 篇原创文章。
#    如果你想尝试获取所有原创文章，可以将此值设置得非常大，例如 99999。
TOTAL_ARTICLES_TO_FETCH = 10 #默认导出10篇，你可以根据需要修改

# 5. OUTPUT_DIR: 导出的 Markdown 文件存放的文件夹名称。
OUTPUT_DIR = "wechat_original_articles_md"

# 新增：用于断点续传的状态文件名
STATE_FILE = "exporter_state.json"
# 新增：用于记录已成功处理的文章，实现增量下载
PROCESSED_ARTICLES_FILE = "processed_articles_record.json"
# 新增：运行模式配置（增量还是全量）
# True: 增量模式（更高效，遇到已处理文章就停止获取）
# False: 全量模式（获取所有文章，然后与已处理记录比对）
INCREMENTAL_MODE = True # 默认使用增量模式，更高效

# 新增：增量模式下，连续几篇文章已处理时停止获取
# 这是为了防止因为偶然的文章顺序变动导致提前停止
INCREMENTAL_STOP_AFTER_CONSECUTIVE = 3  # 连续遇到3篇已处理文章才停止

# 新增：是否保留状态文件（用于记录分页位置）
# True: 保留状态文件，记录最后一次获取的分页位置，下次直接从该位置继续
# False: 每次运行完成后删除状态文件
KEEP_STATE_FILE = True  # 默认保留状态文件

# --- 配置区结束 ---


# --- 全局变量 ---
# HTTP 请求头，模拟浏览器访问
HEADERS = {
    'Cookie': COOKIE_STRING,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 新的文章列表接口 URL 模板 (基于用户提供的新链接)
# 注意：此 URL 预计返回 HTML 页面，而不是 JSON 数据。
# {token}, {begin}, {count} 是占位符。
ARTICLE_LIST_URL_TEMPLATE = (
    "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?"
    "sub=list&begin={begin}&count={count}&token={token}&lang=zh_CN"
)

# --- 函数定义 ---

def sanitize_filename(filename):
    """
    清洗文件名，移除或替换 Windows 文件系统中不允许的字符。
    参数:
        filename (str): 原始文件名 (通常是文章标题)。
    返回:
        str: 清洗后的、适合用作文件名的字符串。
    """
    # 移除 Windows 文件名中的非法字符: \ / : * ? " < > |
    cleaned_filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    # 替换连续的空格为一个空格 (可选)
    cleaned_filename = re.sub(r'\s+', ' ', cleaned_filename).strip()
    # 避免文件名过长 (Windows 文件名长度限制通常是 255 个字符，这里保守一点)
    return cleaned_filename[:150]

def get_original_article_infos(token, total_articles_to_fetch): # 移除了 fakeid 参数
    """
    从微信公众号后台获取指定数量的原创文章的标题和阅读链接。
    参数:
        token (str): 公众号的 token。
        total_articles_to_fetch (int): 希望获取的文章总数上限。
    返回:
        list: 包含 (文章标题, 文章阅读URL, 发布时间) 元组的列表。如果获取失败或没有原创文章，则返回空列表。
    """
    original_articles = [] # 用于存储原创文章信息的列表
    fetched_count = 0 # 已获取到的原创文章数量
    current_page_begin_index = 0 # 当前请求页的起始文章索引
    articles_per_page = 20 # 每次请求获取的文章数量 (微信后台通常每页5或10篇，与新URL中的count对应)
    consecutive_empty_original_pages = 0 # 新增：连续未找到原创文章的页面计数
    max_consecutive_empty_pages = 10 # 新增：如果连续这么多页没找到新原创，就停止（防止无限循环）

    # --- 新增：加载已处理的文章记录，用于增量更新 ---
    processed_article_urls = set()
    if os.path.exists(PROCESSED_ARTICLES_FILE):
        try:
            with open(PROCESSED_ARTICLES_FILE, "r", encoding="utf-8") as f:
                # 假设记录文件每行一个 URL，或者是一个 JSON 列表
                # 为简单起见，我们先用 JSON 列表存储 URL
                loaded_urls = json.load(f)
                if isinstance(loaded_urls, list):
                    processed_article_urls.update(loaded_urls)
            print(f"从 {PROCESSED_ARTICLES_FILE} 加载了 {len(processed_article_urls)} 条已处理文章的记录。")
        except Exception as e:
            print(f"加载 {PROCESSED_ARTICLES_FILE} 失败: {e}。本次将获取所有文章信息（已下载的仍会跳过）。")
    # --- 已处理文章加载结束 ---

    # --- 尝试加载单次运行的断点续传状态 ---
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                original_articles = state_data.get("articles", [])
                # 确保 original_articles 中的每个元素都是元组 (title, url)
                original_articles = [tuple(item) if isinstance(item, list) else item for item in original_articles]

                fetched_count = len(original_articles)
                current_page_begin_index = state_data.get("next_begin_index", 0)
                # consecutive_empty_original_pages 也可以考虑保存和恢复，但通常从0开始问题不大
                print(f"从 {STATE_FILE} 加载状态成功。")
                print(f"  已加载 {fetched_count} 篇文章信息。")
                print(f"  将从 begin_index = {current_page_begin_index} 继续获取。")
        except Exception as e:
            print(f"加载状态文件 {STATE_FILE} 失败: {e}。将从头开始获取。")
            # 如果加载失败，确保变量是初始状态
            original_articles = []
            fetched_count = 0
            current_page_begin_index = 0
    # --- 加载状态结束 ---

    print("开始从微信后台获取原创文章列表 (使用新的URL格式)...")

    # 增量模式相关计数器
    consecutive_processed_articles = 0  # 连续遇到的已处理文章数量
    
    # 循环请求，直到获取到足够数量的原创文章或没有更多文章为止
    while True:
        if fetched_count >= TOTAL_ARTICLES_TO_FETCH: # 如果用户设置了上限，则遵守
            print(f"已达到用户设置的获取上限 ({TOTAL_ARTICLES_TO_FETCH} 篇)，停止获取。")
            break

        # --- 新增：用于判断本页是否已接触到之前处理过的文章 ---
        found_previously_processed_article_on_page = False
        # ---

        # 构建当前页的文章列表请求 URL (不再需要 fakeid)
        request_url = ARTICLE_LIST_URL_TEMPLATE.format(
            token=token,
            begin=current_page_begin_index,
            count=articles_per_page
        )

        print(f"正在请求文章列表第 {current_page_begin_index // articles_per_page + 1} 页: {request_url}")

        try:
            # 发送 GET 请求
            response = requests.get(request_url, headers=HEADERS, timeout=20) # 设置超时时间为20秒
            response.raise_for_status() # 如果 HTTP 请求返回错误状态码 (如 403, 500), 则抛出异常
            response.encoding = response.apparent_encoding # 尝试自动检测编码
            if response.encoding.lower() != 'utf-8':
                response.encoding = 'utf-8'

            # --- 重要：开始解析 HTML ---
            # 检查是否返回了登录页面，这通常表示 Cookie 失效
            if "请重新登录" in response.text or "用户登录" in response.text:
                print("错误：访问文章列表时被要求重新登录。")
                print("请确保 COOKIE_STRING 是最新的，并且对于 mp.weixin.qq.com 有效。")
                print(f"访问的URL: {request_url}")
                print(f"提示：你可能需要重新从浏览器开发者工具中复制最新的 Cookie。")
                break # Cookie 失效，无法继续

            # soup = BeautifulSoup(response.text, 'html.parser') # 不再直接用bs4解析整个页面找列表

            # 新的解析逻辑：从 JavaScript 中提取 JSON 数据
            publish_page_data = None
            # 正则表达式匹配 "publish_page = {...};" 或 "publish_page={...};" (允许等号前后有空格)
            # 使用 re.DOTALL 使 . 可以匹配换行符
            match = re.search(r"publish_page\s*=\s*({.*?});", response.text, re.DOTALL)
            if match:
                json_str = match.group(1) # 获取括号匹配的 JSON 字符串部分
                try:
                    publish_page_data = json.loads(json_str) # 解析最外层 JSON
                except json.JSONDecodeError as e:
                    print(f"  解析页面中的 publish_page JSON 数据失败: {e}")
                    print(f"  提取到的 JSON 字符串片段: {json_str[:500]}...")
                    break # 如果解析失败，无法继续当前页
            else:
                print("  未能从页面脚本中找到 publish_page 数据。")
                # --- 保留之前的调试代码，万一正则匹配失败，可以查看页面内容 ---
                debug_html_filename = "debug_page_content.html"
                try:
                    with open(debug_html_filename, "w", encoding="utf-8") as f:
                        f.write(response.text)
                    print(f"  为了帮助调试，已将当前请求页面的HTML内容保存到: {os.path.join(os.getcwd(), debug_html_filename)}")
                except Exception as e_debug:
                    print(f"  保存调试HTML文件时出错: {e_debug}")
                # --- 调试代码结束 ---
                break # 没有数据源，跳出循环

            if not publish_page_data or 'publish_list' not in publish_page_data:
                print("  publish_page 数据中没有找到 'publish_list'。")
                break

            publish_list = publish_page_data.get('publish_list', [])
            if not publish_list:
                print("  当前页的 publish_list 为空或不存在，可能已获取所有文章。")
                break

            page_found_original_count = 0
            for item in publish_list:
                publish_info_str = item.get('publish_info')
                if not publish_info_str:
                    continue

                try:
                    # publish_info 是一个 JSON 字符串，可能包含 HTML 实体如 &quot;
                    publish_info_unescaped = html.unescape(publish_info_str)
                    publish_info_data = json.loads(publish_info_unescaped)
                except json.JSONDecodeError as e:
                    print(f"    解析 publish_info JSON 失败: {e}")
                    print(f"    publish_info 字符串 (反转义后): {publish_info_unescaped[:500]}...")
                    continue # 跳过这个损坏的 item

                appmsg_list = publish_info_data.get('appmsg_info', [])
                for appmsg in appmsg_list:
                    title = appmsg.get('title')
                    article_url = appmsg.get('content_url')
                    # 原创判断：copyright_type == 1 表示原创
                    # 或者 copyright_status == 11 也可能表示原创 (根据debug_page_content.html)
                    # 我们优先使用 copyright_type
                    is_original = (appmsg.get('copyright_type') == 1)

                    # --- 新增：提取发布时间 ---
                    # 尝试从多个可能的字段中获取发布时间
                    publish_time = None
                    # 可能的时间字段及其获取顺序（优先级从高到低）
                    time_fields = [
                        # 1. 尝试直接从 msg_info 中获取
                        appmsg.get('publish_time'),  # 发布时间
                        appmsg.get('create_time'),   # 创建时间
                        appmsg.get('update_time'),   # 更新时间
                        # 2. 尝试从 publish_info 的根级字段获取
                        publish_info_data.get('publish_time'),
                        publish_info_data.get('create_time'),
                        publish_info_data.get('update_time'),
                        # 3. 尝试从 publish_info 的 sent_info 子字段获取（如果存在）
                        publish_info_data.get('sent_info', {}).get('time')
                    ]
                    
                    # 使用第一个非空、非零的时间值
                    for time_val in time_fields:
                        if time_val:  # 检查非空
                            try:
                                # 通常时间戳是整数，但也可能是字符串
                                timestamp = int(time_val)
                                if timestamp > 0:  # 确保是有效时间戳
                                    publish_time = timestamp
                                    break
                            except (ValueError, TypeError):
                                # 如果无法转换为整数，尝试下一个字段
                                continue
                    
                    # 如果所有字段都没有找到有效时间，使用当前时间作为后备
                    if not publish_time:
                        publish_time = int(time.time())
                        print(f"  警告: 无法从文章数据中提取发布时间，使用当前时间作为替代: {publish_time}")
                    # --- 提取发布时间结束 ---

                    if title and article_url and is_original:
                        # 确保链接是完整的
                        if not article_url.startswith('http'):
                            article_url = "https://mp.weixin.qq.com" + article_url # 拼接域名
                        
                        # --- 增量下载检查 ---
                        if article_url in processed_article_urls:
                            print(f"  文章 《{title}》 (URL: {article_url}) 已在之前处理过记录中，跳过加入列表。")
                            found_previously_processed_article_on_page = True
                            consecutive_processed_articles += 1  # 增加连续已处理文章计数
                            
                            # 增量模式下，如果连续发现太多已处理文章，提前结束获取
                            if INCREMENTAL_MODE and consecutive_processed_articles >= INCREMENTAL_STOP_AFTER_CONSECUTIVE:
                                print(f"  增量模式：已连续遇到 {consecutive_processed_articles} 篇已处理文章，即将停止获取。")
                                break
                            
                            continue # 跳过这个已处理的文章，检查本publish_info中的下一篇appmsg

                        print(f"  找到原创文章: 《{title}》")
                        # 发布时间的可读形式，用于打印
                        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(publish_time))
                        print(f"  发布时间: {time_str}")
                        
                        # 将发布时间加入到文章信息元组中
                        original_articles.append((title, article_url, publish_time))
                        fetched_count += 1
                        page_found_original_count += 1
                        if fetched_count >= total_articles_to_fetch:
                            break # 已达到目标数量
                    elif title and article_url and not is_original:
                        # print(f"  跳过非原创文章: 《{title}》 (copyright_type: {appmsg.get('copyright_type')})")
                        pass # 可以取消注释上面一行来查看非原创文章信息

                if fetched_count >= total_articles_to_fetch:
                    break # 已达到目标数量
            
            if page_found_original_count == 0 and found_previously_processed_article_on_page:
                print("  当前页未找到新的原创文章，且已遇到之前处理过的文章，推测后续均为旧文章，停止获取链接。")
                break # 退出主循环 (while True)
            
            if page_found_original_count == 0:
                print("  当前页未找到新的原创文章。")
                consecutive_empty_original_pages += 1 # 增加空页计数
                if consecutive_empty_original_pages >= max_consecutive_empty_pages:
                    print(f"  已连续 {max_consecutive_empty_pages} 页未找到新的原创文章，假定已无更多原创文章。")
                    break # 退出主循环
            else:
                consecutive_empty_original_pages = 0 # 如果找到了原创文章，重置空页计数

            # 判断是否还有更多页面可以请求
            # publish_page_data 中有 total_count, publish_count, masssend_count
            # publish_list 是当前页的群发条目列表
            # appmsg_info 是单个群发条目中的图文列表
            # 我们主要关心的是 publish_list 是否为空，如果为空，说明服务器没有返回更多群发记录了
            if not publish_list: # 这个判断在前面已经有了，这里是双重保险
                print("  publish_list 为空，确认已无更多文章可供处理。")
                break

            # 检查是否是最后一页的另一种方式：如果返回的条目数少于请求的条目数
            # （注意：这只在服务器确实不多不少返回数据时准确）
            if len(publish_list) < articles_per_page:
                print(f"  当前页返回的群发条目数 ({len(publish_list)}) 少于请求数 ({articles_per_page})，可能已是最后一页。")
                # 即使这样，也让循环再试一次，由 consecutive_empty_original_pages 来最终决定
                # break # 可以考虑在这里直接退出，但为了更保险，让连续空页机制来判断

            # 更新到下一页的起始索引
            current_page_begin_index += articles_per_page
            # 请求间隔，避免过于频繁
            print(f"  本页处理完毕，等待 3 秒后请求下一页...")
            time.sleep(3)

            # --- 新增：每处理完一页，保存当前状态 (用于单次运行中断恢复) ---
            try:
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    state_to_save = {
                        "articles": original_articles,
                        "next_begin_index": current_page_begin_index + articles_per_page,
                        "last_update_time": int(time.time()),
                        "last_article_count": len(original_articles),
                        "version": "1.0"  # 添加版本号便于后续格式变更
                    }
                    json.dump(state_to_save, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"保存状态到 {STATE_FILE} 失败: {e}")
            # --- 保存状态结束 ---

            # 增量模式的判断逻辑优化
            if INCREMENTAL_MODE:
                if found_previously_processed_article_on_page and page_found_original_count == 0:
                    print(f"  增量模式：本页未找到新的原创文章且遇到了已处理文章，停止获取更多页面。")
                    break

        except requests.exceptions.Timeout:
            print(f"请求文章列表超时: {request_url}")
            print("请检查网络连接或稍后再试。")
            break
        except requests.exceptions.RequestException as e:
            print(f"请求文章列表时发生网络错误: {e}")
            break
        except Exception as e:
            print(f"获取文章列表过程中发生未知错误: {e}")
            break

    if not original_articles:
        print("未能获取到任何原创文章信息。请检查：")
        print("1. COOKIE_STRING, TOKEN 是否配置正确且有效。")
        print("2. 网络连接是否正常。")
        print("3. 你的公众号是否有原创文章。")
        print(f"4. ARTICLE_LIST_URL_TEMPLATE ('{ARTICLE_LIST_URL_TEMPLATE}') 是否正确。")
        print(f"5. 如果脚本尝试解析HTML，请确认HTML元素选择器 (在 get_original_article_infos 函数中) 是否与你公众号后台页面结构匹配。")

    return original_articles


def get_article_html_content(article_url):
    """
    获取单篇文章的 HTML 主体内容。
    参数:
        article_url (str): 文章的阅读链接。
    返回:
        str: 文章主体部分的 HTML 字符串。如果获取失败，则返回 None。
    """
    print(f"  正在获取文章内容: {article_url}")
    try:
        response = requests.get(article_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        # 确保正确解码响应内容，微信文章通常是 utf-8
        response.encoding = response.apparent_encoding # 尝试自动检测编码
        if response.encoding.lower() != 'utf-8': # 如果自动检测不是utf-8，强制设为utf-8
            response.encoding = 'utf-8'


        # 使用 BeautifulSoup 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 微信文章正文通常在 id="js_content" 的 div 元素中
        # 或者 class="rich_media_content"
        content_div = soup.find('div', id='js_content')
        if not content_div: # 如果没找到 id='js_content'
            content_div = soup.find('div', class_='rich_media_content') # 尝试 class='rich_media_content'

        if content_div:
            return str(content_div) # 返回该 div 元素的 HTML 内容字符串
        else:
            print(f"  警告: 未能在文章页面 {article_url} 中找到主要内容区域 (id='js_content' 或 class_='rich_media_content')。")
            # print(f"  部分页面HTML: {response.text[:1000]}") # 打印部分HTML用于调试
            return None

    except requests.exceptions.Timeout:
        print(f"  获取文章内容超时: {article_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  获取文章 {article_url} 内容时发生网络错误: {e}")
        return None
    except Exception as e:
        print(f"  处理文章 {article_url} 时发生未知错误: {e}")
        return None

def convert_html_to_markdown(html_content, article_title):
    """
    将 HTML 内容转换为 Markdown 格式，并在开头添加文章标题。
    参数:
        html_content (str): 文章的 HTML 内容字符串。
        article_title (str): 文章的标题。
    返回:
        str: 转换后的 Markdown 格式文本。
    """
    # 初始化 html2text 转换器
    h2t = html2text.HTML2Text()

    # 配置转换器选项
    h2t.ignore_links = False  # False 表示不忽略链接，会保留链接
    h2t.ignore_images = True  # True 表示忽略图片，不转换图片标签
    h2t.body_width = 0        # 设置为0表示不自动换行，尽量保持原文的换行
    h2t.unicode_snob = True   # 更好地处理 Unicode 字符
    h2t.escape_snob = True    # 避免不必要的字符转义

    # 转换 HTML 到 Markdown
    markdown_text = h2t.handle(html_content)

    # 在 Markdown 文本的开头添加一级标题 (文章标题)
    # Markdown 语法中，"# 标题内容" 表示一级标题
    # 标题和正文之间通常需要一个空行
    final_markdown = f"# {article_title}\n\n{markdown_text}"
    return final_markdown

def save_markdown_to_file(title, markdown_content, output_dir, publish_time=None):
    """
    将 Markdown 内容保存到文件，文件名使用文章标题生成。
    参数:
        title (str): 文章标题，用于生成文件名。
        markdown_content (str): 要保存的 Markdown 内容。
        output_dir (str): 输出目录路径。
        publish_time (int, optional): 文章发布时间的 Unix 时间戳。
    """
    try:
        # 确保输出目录存在
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                print(f"已创建输出文件夹: {output_dir}")
            except OSError as e:
                print(f"创建输出文件夹 {output_dir} 失败: {e}")
                return  # 创建失败则无法保存，直接返回
        
        # 清洗文件名
        safe_title = sanitize_filename(title)
        
        # 文件名可以选择性地包含发布日期
        # 将时间戳转换为日期字符串 (YYYYMMDD)
        date_prefix = ""
        if publish_time:
            date_prefix = time.strftime("%Y%m%d_", time.localtime(publish_time))
        
        # 决定是否使用日期前缀（这里我们暂时不使用，以保持向后兼容）
        #filepath = os.path.join(output_dir, f"{date_prefix}{safe_title}.md")
        filepath = os.path.join(output_dir, f"{safe_title}.md")
        
        # 为 Markdown 内容添加发布时间元数据（Front Matter）
        if publish_time:
            date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(publish_time))
            # 使用 YAML Front Matter 格式（---开始和结束）
            front_matter = f"""---
title: "{title}"
date: {date_str}
---

"""
            # 在 Markdown 内容前添加 Front Matter
            markdown_content = front_matter + markdown_content
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"  成功保存文章到: {filepath}")
    except IOError as e:
        print(f"  保存文件 {filepath} 时发生 IO 错误: {e}")
    except Exception as e:
        print(f"  保存文件 {filepath} 时发生未知错误: {e}")

# --- 辅助函数区 (可以放在其他函数定义之后，main函数之前) ---

# 创建一个简单的日志函数，用于记录跳过的文章 (可选，但有助于追踪)
# 你也可以将这些信息直接打印或写入 bug.md
LOG_FILE = "processing_log.txt" # 日志文件名

def ensure_log_file_exists():
    """确保日志文件存在，如果不存在则创建并写入头部信息"""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"微信文章导出处理日志 ({time.strftime('%Y-%m-%d %H:%M:%S')})\n")
            f.write("=" * 30 + "\n")

def log_skip_event(message):
    """记录跳过事件到日志文件"""
    ensure_log_file_exists()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception as e:
        print(f"写入日志失败: {e}")

def load_processed_articles():
    """加载已处理的文章URL集合"""
    processed_urls = set()
    if os.path.exists(PROCESSED_ARTICLES_FILE):
        try:
            with open(PROCESSED_ARTICLES_FILE, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)
                if isinstance(loaded_data, list):
                    # 旧格式：简单的URL列表
                    processed_urls.update(loaded_data)
                elif isinstance(loaded_data, dict):
                    # 新格式：字典，键是URL，值是元数据
                    processed_urls.update(loaded_data.keys())
            print(f"从 {PROCESSED_ARTICLES_FILE} 加载了 {len(processed_urls)} 条已处理文章的记录。")
        except Exception as e:
            print(f"加载 {PROCESSED_ARTICLES_FILE} 失败: {e}。")
    return processed_urls

def save_processed_article(article_url, processed_urls_set, publish_time=None):
    """
    将新处理的文章URL添加到集合并保存到文件
    
    参数:
        article_url (str): 文章URL
        processed_urls_set (set): 已处理文章URL的集合
        publish_time (int, optional): 文章发布时间的Unix时间戳
    """
    # 在当前版本下，processed_urls_set 是一个简单的URL集合
    # 我们可以将其升级为一个字典，键是URL，值是发布时间和处理时间
    # 但为了保持向后兼容，我们先检查 PROCESSED_ARTICLES_FILE 的格式
    
    article_data = {}
    try:
        if os.path.exists(PROCESSED_ARTICLES_FILE):
            with open(PROCESSED_ARTICLES_FILE, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)
                
                # 判断当前格式是列表还是字典
                if isinstance(loaded_data, list):
                    # 旧格式是URL列表，我们将其转换为字典
                    article_data = {url: {"processed_at": int(time.time())} for url in loaded_data}
                elif isinstance(loaded_data, dict):
                    # 已经是字典格式
                    article_data = loaded_data
        
        # 如果文章不存在，或者需要更新时间信息
        if article_url not in article_data or (publish_time and "publish_time" not in article_data[article_url]):
            current_time = int(time.time())
            if article_url not in article_data:
                article_data[article_url] = {"processed_at": current_time}
            
            # 添加或更新发布时间
            if publish_time:
                article_data[article_url]["publish_time"] = publish_time
            
            # 保存更新后的数据
            with open(PROCESSED_ARTICLES_FILE, "w", encoding="utf-8") as f:
                json.dump(article_data, f, ensure_ascii=False, indent=4)
            # print(f"  文章 {article_url} 已记录到 {PROCESSED_ARTICLES_FILE}")
        
        # 更新内存中的URL集合（仅包含URL，不含元数据）
        processed_urls_set.add(article_url)
        
    except Exception as e:
        print(f"  保存已处理文章记录到 {PROCESSED_ARTICLES_FILE} 失败: {e}")


# --- 主逻辑执行区 ---
def download_and_save_article(article_info, index, total, current_processed_urls):
    """
    下载并保存单篇文章的函数，用于并行处理
    
    参数:
        article_info: 文章信息元组 (title, article_url, publish_time)
        index: 当前文章索引
        total: 文章总数
        current_processed_urls: 已处理文章URL集合
    
    返回:
        dict: 包含处理结果信息的字典
    """
    # 解析文章信息
    if len(article_info) == 3:
        title, article_url, publish_time = article_info
    else:
        title, article_url = article_info
        publish_time = None
    
    print(f"--- 开始处理第 {index + 1}/{total} 篇原创文章: 《{title}》 ---")
    if publish_time:
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(publish_time))
        print(f"  发布时间: {time_str}")
    
    # 检查文件是否已存在
    safe_title = sanitize_filename(title)
    output_filename = os.path.join(OUTPUT_DIR, f"{safe_title}.md")
    
    if os.path.exists(output_filename):
        print(f"  文件 '{output_filename}' 已存在，跳过下载和转换。")
        log_skip_event(f"文件已存在，跳过: {title}")
        print("-" * 30)
        return {"title": title, "status": "skipped", "reason": "file_exists"}
    
    # 获取文章内容
    html_content = get_article_html_content(article_url)
    
    if html_content:
        # 转换为Markdown
        markdown_content = convert_html_to_markdown(html_content, title)
        # 保存文件
        save_markdown_to_file(title, markdown_content, OUTPUT_DIR, publish_time)
        # 记录已处理
        save_processed_article(article_url, current_processed_urls, publish_time)
        print(f"  文章 《{title}》 已成功处理并记录。")
        print("-" * 30)
        return {"title": title, "status": "success"}
    else:
        print(f"  未能获取文章 《{title}》 的内容，已跳过。")
        print("-" * 30)
        return {"title": title, "status": "failed", "reason": "content_not_available"}

def print_state_info():
    """打印状态文件的内容，让用户了解当前保存的状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                articles = state_data.get("articles", [])
                next_begin = state_data.get("next_begin_index", 0)
                last_update = state_data.get("last_update_time", 0)
                last_count = state_data.get("last_article_count", 0)
                
                print("\n状态文件信息:")
                print(f"  上次更新时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_update))}")
                print(f"  已记录文章数: {last_count}")
                print(f"  下次开始位置: begin_index = {next_begin}")
                
                # 可选：显示最近几篇文章
                if articles:
                    print("\n  最近几篇记录的文章:")
                    for i, article in enumerate(articles[-5:]):  # 只显示最后5篇
                        if len(article) >= 2:
                            title = article[0]
                            url = article[1]
                            print(f"    {i+1}. 《{title}》")
                            # print(f"       {url}")  # 可选是否显示URL
                
                print("\n要从头开始获取文章，请删除状态文件或设置 KEEP_STATE_FILE = False")
                
        except Exception as e:
            print(f"读取状态文件失败: {e}")
    else:
        print("未找到状态文件，将从头开始获取文章。")

def main():
    """
    脚本的主执行函数。
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='微信公众号原创文章导出工具')
    parser.add_argument('--reset', action='store_true', help='忽略状态文件，从头开始获取')
    parser.add_argument('--mode', choices=['incremental', 'full'], 
                       help='运行模式: incremental(增量)或full(全量)')
    parser.add_argument('--info', action='store_true', help='只显示状态信息，不执行下载')
    args = parser.parse_args()
    
    # 处理只显示信息的选项
    if args.info:
        print_state_info()
        return
    
    # 处理重置选项
    if args.reset and os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
            print(f"已删除状态文件 {STATE_FILE}，将从头开始获取文章。")
        except Exception as e:
            print(f"删除状态文件失败: {e}")
    
    # 处理模式选项
    global INCREMENTAL_MODE
    if args.mode:
        INCREMENTAL_MODE = (args.mode == 'incremental')
        print(f"通过命令行参数设置运行模式为: {'增量' if INCREMENTAL_MODE else '全量'}")
    
    print("微信公众号原创文章导出脚本 (Markdown格式)")
    print("=" * 40)

    # 检查用户配置是否基本完整
    if "在此处粘贴" in COOKIE_STRING or not COOKIE_STRING:
        print("错误: COOKIE_STRING 未配置或配置不正确。请仔细阅读脚本开头的注释并填写。")
        return
    if "在此处粘贴" in TOKEN or not TOKEN:
        print("错误: TOKEN 未配置。请从公众号后台URL中找到并填写。")
        return
    # FAKEID 的检查可以暂时保留，但如果新URL确实不需要它，此检查的严格性可以降低
    if "在此处粘贴" in FAKEID or not FAKEID:
        print("提示: FAKEID 未配置。如果新的文章列表URL不需要FAKEID，此项可以忽略。")
        # return # 根据新URL，fakeid可能不再是必须的，所以不直接退出

    if TOTAL_ARTICLES_TO_FETCH <= 0:
        print("错误: TOTAL_ARTICLES_TO_FETCH 必须是一个大于0的数字。")
        return

    print(f"配置信息:")
    print(f"  - Token: {'*' * (len(TOKEN) - 3) + TOKEN[-3:] if len(TOKEN) > 3 else TOKEN}") # 简单脱敏显示
    # print(f"  - FakeID: {FAKEID}") # FakeID 可能不再使用，可以注释掉此行
    print(f"  - 计划导出文章数: {TOTAL_ARTICLES_TO_FETCH}")
    print(f"  - 输出目录: {OUTPUT_DIR}")
    print(f"  - 状态文件(单次运行中断恢复): {STATE_FILE}")
    print(f"  - 已处理记录(增量下载): {PROCESSED_ARTICLES_FILE}")
    print(f"  - 跳过/错误日志将记录在: {LOG_FILE}") # 提示日志文件位置
    print(f"  - 运行模式: {'增量' if INCREMENTAL_MODE else '全量'}")
    print(f"  - 增量停止阈值: 连续{INCREMENTAL_STOP_AFTER_CONSECUTIVE}篇已处理")
    print("-" * 40)

    # 确保输出目录存在
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
            print(f"输出目录 '{OUTPUT_DIR}' 已创建。")
        except OSError as e:
            print(f"创建输出目录 '{OUTPUT_DIR}' 失败: {e}")
            return  # 创建失败则直接返回，避免继续执行

    # 如果保留状态文件，显示状态信息
    if KEEP_STATE_FILE:
        print_state_info()

    # 1. 获取原创文章的标题和链接列表
    # 调用时不再传递 fakeid
    article_infos = get_original_article_infos(TOKEN, TOTAL_ARTICLES_TO_FETCH)

    if not article_infos:
        print("未能获取到任何原创文章信息，脚本执行结束。")
        # --- 新增：如果获取失败，也尝试清理状态文件，避免下次错误加载 ---
        if os.path.exists(STATE_FILE):
            try:
                # 如果是因为获取了0篇文章而结束，但状态文件可能还记录了之前的页码，
                # 这种情况下保留状态文件可能是合理的，以便下次从该页码尝试。
                # 但如果是因为错误（如cookie失效）导致0篇，则清理可能更好。
                # 暂时先不在这里主动删除，让get_original_article_infos成功完成后删除。
                pass
            except Exception as e_del:
                print(f"清理状态文件 {STATE_FILE} 时出错: {e_del}")
        return

    print(f"\n成功获取到 {len(article_infos)} 篇原创文章的信息，准备并行处理...\n")

    # --- 新增：获取文章列表成功后，根据配置决定是否删除状态文件 ---
    if os.path.exists(STATE_FILE) and not KEEP_STATE_FILE:
        try:
            os.remove(STATE_FILE)
            print(f"已成功获取所有文章链接，临时状态文件 {STATE_FILE} 已删除。")
        except Exception as e_del:
            print(f"删除状态文件 {STATE_FILE} 失败: {e_del}")
    elif KEEP_STATE_FILE:
        print(f"状态文件 {STATE_FILE} 已保留，下次运行可从当前位置继续。")
    # --- 删除状态文件逻辑结束 ---

    # 2. 遍历文章列表，获取内容、转换并保存
    # --- 获取最新的已处理文章集合，用于实时更新 ---
    # 再次加载，确保拿到的是最新的，虽然 get_original_article_infos 内部也加载了，
    # 但那个是用于过滤获取列表的，这里是用于更新的。
    # 或者，让 get_original_article_infos 返回它加载的 processed_article_urls 集合。
    # 为简单起见，这里重新加载一次。
    current_processed_urls = load_processed_articles()
    # ---

    # 设置并行下载的最大线程数
    # 不要设置太高，避免触发微信的限流或防爬机制
    # 建议根据网络条件调整，一般3-5个比较安全
    max_workers = 3
    
    print(f"设置并行下载线程数: {max_workers}")
    
    # 使用线程池并行下载和处理文章
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有下载任务
        future_to_article = {
            executor.submit(
                download_and_save_article, 
                article_info, 
                index, 
                len(article_infos),
                current_processed_urls
            ): (index, article_info) 
            for index, article_info in enumerate(article_infos)
        }
        
        # 处理完成的任务
        for future in concurrent.futures.as_completed(future_to_article):
            index, article_info = future_to_article[future]
            try:
                result = future.result()
                # 这里可以添加处理结果的统计逻辑
            except Exception as e:
                print(f"处理文章时发生错误: {e}")
    
    print("\n所有指定的原创文章处理完毕！")
    print(f"导出的 Markdown 文件已保存到 '{os.path.join(os.getcwd(), OUTPUT_DIR)}' 目录下。")
    # 确保在所有操作成功完成后，根据配置决定是否删除状态文件
    if os.path.exists(STATE_FILE) and not KEEP_STATE_FILE:
        try:
            os.remove(STATE_FILE)
            print(f"最终清理：临时状态文件 {STATE_FILE} 已删除。")
        except Exception as e_del:
            print(f"最终清理状态文件 {STATE_FILE} 失败: {e_del}")
    elif KEEP_STATE_FILE:
        print(f"状态文件 {STATE_FILE} 已保留，记录了当前处理位置。")
    print("=" * 40)

# 当脚本作为主程序运行时，执行 main() 函数
if __name__ == '__main__':
    # 记录脚本开始运行的时间
    script_start_time = time.time()
    main() # 调用主函数
    # 计算脚本总运行时间
    script_end_time = time.time()
    total_run_time = script_end_time - script_start_time
    print(f"脚本总运行时间: {total_run_time:.2f} 秒。")
