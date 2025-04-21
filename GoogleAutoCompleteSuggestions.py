"""
GoogleAutoCompleteSuggestions.py

功能说明:
    该脚本使用 Selenium 自动化工具从谷歌搜索中获取下拉建议，并将结果保存到本地文件中。
    用户可以输入一个词根，程序将生成相关的查询字符串并获取建议。

使用方法:
    1. 确保已安装 Python 和 Selenium 库。
    2. 安装 Chrome 浏览器和相应的 ChromeDriver。
    3. 运行脚本，输入需要搜索的词根。
    4. 程序将生成以词根命名的文本文件，保存获取到的搜索建议。

依赖项:
    - Python 3.x
    - Selenium
    - Chrome 浏览器
    - ChromeDriver

作者: aidaox
"""
import os  # 操作系统相关
import json  # 进度保存
import time  # 时间相关
import random  # 随机延迟
from selenium import webdriver  # Selenium主库
from selenium.webdriver.common.by import By  # 元素定位
from selenium.webdriver.common.keys import Keys  # 键盘操作
from selenium.webdriver.support.ui import WebDriverWait  # 显式等待
from selenium.webdriver.support import expected_conditions as EC  # 等待条件
from selenium.common.exceptions import TimeoutException, NoSuchElementException, InvalidSessionIdException, WebDriverException  # 异常

def create_driver(headless, user_agents):
    """
    创建并返回一个新的 Selenium Chrome driver
    :param headless: 是否无头模式
    :param user_agents: 用户代理列表
    :return: 新的 driver 实例
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-sync')
    options.add_argument("--lang=en")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-agent={random.choice(user_agents)}")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1366, 768)
    driver.set_page_load_timeout(30)
    return driver

def get_google_suggestions(driver, query, previous_query=None, max_retries=3, create_driver_func=None):
    """
    使用Selenium获取谷歌搜索下拉列表的关键词
    :param driver: Selenium WebDriver实例
    :param query: 用户输入的查询字符串
    :param previous_query: 上一次的查询字符串，用于决定是否需要刷新页面
    :param max_retries: 最大重试次数
    :param create_driver_func: 创建新的driver的函数
    :return: 返回下拉列表的关键词
    """
    need_refresh = True  # 是否需要刷新页面
    common_prefix_length = 0  # 当前和上一次查询的共同前缀长度
    force_refresh = False  # 是否强制刷新页面

    # 判断是否需要刷新页面
    if previous_query:
        # 分析当前查询和上一次查询的共同前缀
        min_length = min(len(query), len(previous_query))
        for i in range(min_length):
            if query[i] == previous_query[i]:
                common_prefix_length += 1
            else:
                break
        
        # 获取查询中词根后的首字母位置
        root_term_length = len(query.split()[0]) + 1  # 词根长度+空格
        
        # 检查首字母是否变化（例如从'a'系列到'b'系列）
        if (len(query) > root_term_length and 
            len(previous_query) > root_term_length and 
            query[root_term_length] == previous_query[root_term_length]):
            # 首字母相同，可以尝试增量更新
            if common_prefix_length >= root_term_length + 1:  # 确保至少包含词根+空格+首字母
                need_refresh = False
                print(f"检测到共同前缀：'{query[:common_prefix_length]}'，尝试增量更新")
        else:
            # 首字母变化，强制刷新页面
            prev_letter = previous_query[root_term_length] if len(previous_query) > root_term_length else '无'
            curr_letter = query[root_term_length] if len(query) > root_term_length else '无'
            print(f"检测到首字母变化（{prev_letter} -> {curr_letter}），强制刷新页面")
            need_refresh = True
            force_refresh = True  # 标记为强制刷新
    
    # 添加重试机制
    for attempt in range(max_retries):
        try:
            # 检查是否必须刷新页面
            if need_refresh or force_refresh or driver.current_url != "https://www.google.com/":
                print("刷新页面...")
                driver.get("https://www.google.com/")
            # 等待搜索框
            try:
                search_box = WebDriverWait(driver, 15).until(
                    EC.visibility_of_element_located((By.NAME, "q"))
                )
            except Exception as e:
                print(f"等待搜索框时出错 (尝试 {attempt+1}/{max_retries}): {e}")
                continue  # 重试

            # 输入内容
            if need_refresh or force_refresh:
                search_box.clear()
                    
                # 模拟人类输入 - 逐字符输入并添加随机延迟
                for char in query:
                    search_box.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))  # 随机输入延迟
            else:
                # 不需要刷新页面，只修改搜索词
                search_box = driver.find_element(By.NAME, "q")
                current_text = search_box.get_attribute("value")
                print(f"搜索框当前内容: '{current_text}'，目标内容: '{query}'")
                
                # 添加内容验证 - 如果当前内容与预期不符，强制刷新
                if current_text != query:
                    # 如果首字母不同或格式差异大，直接刷新页面重新输入可能更可靠
                    if (len(current_text) > root_term_length and 
                        len(query) > root_term_length and 
                        current_text[root_term_length] != query[root_term_length]):
                        print(f"搜索框内容首字母与目标不符，强制刷新页面")
                        # 回到外层循环的刷新逻辑
                        need_refresh = True
                        force_refresh = True
                        continue
                    
                    # 处理从"word ab"到"word a b"或从"word a b"到"word ac"等转换
                    # 如果是从紧凑到带空格版本的转换，直接使用输入法处理可能更容易
                    if len(query) == len(current_text) + 1 and " " in query[len(current_text)-1:]:
                        # 可能是插入空格的情况，清空后重新输入可能更可靠
                        search_box.clear()
                        for char in query:
                            search_box.send_keys(char)
                            time.sleep(random.uniform(0.05, 0.15))
                        print(f"特殊情况处理：从 '{current_text}' 完全重新输入为 '{query}'")
                    else:
                        # 计算需要退格的次数
                        backspaces_needed = len(current_text) - common_prefix_length
                        
                        # 发送退格键
                        for _ in range(backspaces_needed):
                            search_box.send_keys(Keys.BACKSPACE)
                            time.sleep(random.uniform(0.05, 0.1))  # 随机退格延迟
                        
                        # 输入新的后缀
                        new_suffix = query[common_prefix_length:]
                        for char in new_suffix:
                            search_box.send_keys(char)
                            time.sleep(random.uniform(0.05, 0.15))  # 随机输入延迟
                        
                        print(f"增量更新：从 '{current_text}' 修改为 '{query}'")
            
            # 等待片刻让谷歌生成建议
            time.sleep(random.uniform(0.8, 1.5))
            
            # 验证更新后的搜索框内容
            search_box = driver.find_element(By.NAME, "q")
            final_text = search_box.get_attribute("value")
            if final_text != query:
                print(f"警告：搜索框内容更新失败！预期: '{query}'，实际: '{final_text}'")
                if attempt < max_retries - 1:
                    print("强制刷新页面并重试...")
                    need_refresh = True
                    force_refresh = True
                    continue
            
            # 使用多个可能的CSS选择器来查找下拉建议
            selectors = [
                "ul[role='listbox'] li",  # 更通用的选择器
                "div.OBMEnb ul.G43f7e li",  # 原选择器
                "div.UUbT9 ul li",  # 另一种可能的选择器
                "div.aajZCb ul li"  # 另一种可能的选择器
            ]
            suggestions = []
            for selector in selectors:
                try:
                    # 增加等待时间
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    suggestion_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    suggestions = [suggestion.text for suggestion in suggestion_elements if suggestion.text]
                    if suggestions:
                        break  # 找到了建议，跳出循环
                except Exception:
                    continue  # 尝试下一个选择器
            
            if not suggestions:
                # 如果所有选择器都失败，尝试按下箭头键触发建议显示
                search_box.send_keys(Keys.DOWN)
                time.sleep(1)
                # 再次尝试获取建议
                for selector in selectors:
                    try:
                        suggestion_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        suggestions = [suggestion.text for suggestion in suggestion_elements if suggestion.text]
                        if suggestions:
                            break
                    except:
                        continue

    # 打印获取到的建议
            print(f"获取到的建议: {suggestions}")
            return suggestions
        except InvalidSessionIdException as e:
            print(f"检测到 driver 会话失效 (尝试 {attempt+1}/{max_retries}): {e}")
            if create_driver_func is not None:
                print("正在重新创建 driver ...")
                driver = create_driver_func()  # 重新创建 driver
            else:
                print("无法重建 driver，请检查 create_driver_func 参数")
            continue  # 继续重试
        except Exception as e:
            print(f"获取建议出错 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = random.uniform(5, 15)
                print(f"等待 {wait_time:.2f} 秒后重试...")
                time.sleep(wait_time)
    print("所有尝试均失败，返回空列表")
    return []

def save_suggestions_to_file(suggestions, filename):
    """
    将建议保存到本地文件，并避免重复
    :param suggestions: 要保存的建议列表
    :param filename: 文件名
    """
    # 先读取文件中已有的建议
    existing_suggestions = set()
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:  # 忽略空行
                    existing_suggestions.add(line)
    
    # 筛选出新的建议
    new_suggestions = []
    for suggestion in suggestions:
        if suggestion and suggestion not in existing_suggestions:  # 确保建议不为空且不重复
            new_suggestions.append(suggestion)
            existing_suggestions.add(suggestion)  # 添加到已存在集合中
    
    # 只追加写入新的建议
    if new_suggestions:
        with open(filename, 'a', encoding='utf-8') as f:
            for suggestion in new_suggestions:
                f.write(suggestion + '\n')  # 每个建议写入一行
        print(f"添加了 {len(new_suggestions)} 条新建议，过滤了 {len(suggestions) - len(new_suggestions)} 条重复建议")
    else:
        print("没有新的建议添加")

def load_progress(filename):
    """从json文件加载进度，返回set集合，查重更快"""
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_progress(queries, filename):
    """保存进度到json文件，set转list"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(list(queries), f)

def optimize_input_strategy(driver, current_text, target_text):
    """根据当前文本和目标文本选择最优的输入策略"""
    search_box = driver.find_element(By.NAME, "q")
    
    # 如果差异很小，尝试增量修改
    if len(target_text) - len(current_text) <= 3 and target_text.startswith(current_text):
        # 只需添加额外字符
        suffix = target_text[len(current_text):]
        for char in suffix:
            search_box.send_keys(char)
            time.sleep(random.uniform(0.05, 0.1))
        return True
    
    # 如果格式差异大，完全清空重新输入
    search_box.clear()
    time.sleep(0.1)
    
    # 字符分组输入，提高效率
    chunks = [target_text[i:i+3] for i in range(0, len(target_text), 3)]
    for chunk in chunks:
        search_box.send_keys(chunk)
        time.sleep(random.uniform(0.1, 0.2))
    
    return True

def get_query_priority(query):
    # 单字母查询通常返回更多结果
    if len(query.split()[0]) == 1:  
        return 3
    # 双字母紧凑查询次之
    elif len(query.split()[0]) == 2 and " " not in query.split()[0]:
        return 2
    # 其他查询优先级较低
    else:
        return 1

def main():
    start_time = time.time()  # 记录开始时间
    # 弹出交互窗口让用户输入需要搜索的词根
    root_word = input("请输入需要搜索的词根: ").strip()  # 去除前后空格
    if not root_word:
        print("词根不能为空，请重新运行程序。")
        return

    # 让用户选择运行模式
    run_mode = input("请选择运行模式 (1=完整查询, 2=快速模式, 3=超快模式): ").strip()

    # 根据模式设置查询范围
    if run_mode == "2":  # 快速模式
        # 只使用高频字母组合
        first_chars = "abcdefghijklmnopqrstuvwxy"[::2]  # 隔一个字母取一个
        second_chars = "abcdefghijklmnopqrstuvwxy"[::2]
        numbers = range(0, 5)  # 只使用0-4
    elif run_mode == "3":  # 超快模式
        # 只使用最常见字母组合
        first_chars = "abcdefghijklm"[::3]  # 隔三个字母取一个
        second_chars = "abcdefghijklm"[::3]
        numbers = range(0, 3)  # 只使用0-2
    else:  # 完整模式
        first_chars = "abcdefghijklmnopqrstuvwxyz"
        second_chars = "abcdefghijklmnopqrstuvwxyz"
        numbers = range(0, 10)

    # 让用户选择搜索模式
    while True:
        search_mode = input("请选择搜索模式 (1=后缀搜索[word a], 2=前缀搜索[a word], 3=两者都搜索): ").strip()
        if search_mode in ['1', '2', '3']:
            break
        print("无效输入，请输入1、2或3")
    
    do_suffix_search = search_mode in ['1', '3']  # 是否执行后缀搜索
    do_prefix_search = search_mode in ['2', '3']  # 是否执行前缀搜索
    
    # 添加选项是否使用无头浏览器
    headless = input("是否使用无头模式来提高速度？(y/n): ").lower() == 'y'

    # 在创建浏览器时
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        
    # 添加其他性能优化参数
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-sync')

    # 增强浏览器配置
    options.add_argument("--lang=en")  # 设置浏览器语言为英文
    options.add_argument("--disable-blink-features=AutomationControlled")  # 隐藏自动化特征
    
    # 添加随机用户代理以模拟不同浏览器
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    ]
    options.add_argument(f"--user-agent={random.choice(user_agents)}")
    
    driver = webdriver.Chrome(options=options)  # 只需打开一次浏览器
    driver.set_window_size(1366, 768)  # 设置窗口大小
    
    # 设置页面加载超时
    driver.set_page_load_timeout(30)

    progress_file = f'{root_word}_progress.json'  # 进度文件名
    processed_queries = load_progress(progress_file)  # 加载已处理的查询

    # 将文件名中的空格替换为下划线
    safe_root_word = root_word.replace(" ", "_")  # 用于文件名的安全词根
    output_file = f'{safe_root_word}.txt'
    
    # 用于跟踪已保存的建议的集合
    saved_suggestions = set()
    
    # 如果输出文件已存在，加载已有的建议到集合中
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    saved_suggestions.add(line)
        print(f"从现有文件加载了 {len(saved_suggestions)} 条建议")

    # 生成查询字符串
    all_queries = []
    
    # 在获取建议后添加智能跳过机制
    empty_results_count = {}  # 记录每种模式的空结果数
    
    # 批量保存结果而不是每次查询后都写文件
    batch_suggestions = []
    
    # 在主函数开始处添加变量
    consecutive_successes = 0
    wait_multiplier = 1.0
    query_count = 0  # 添加查询计数器

    try:
        # 用闭包方式传递 driver 创建参数
        def driver_factory():
            return create_driver(headless, user_agents)

        driver = driver_factory()  # 创建初始 driver

        # 后缀搜索
        if do_suffix_search:
            suffix_start = time.time()
            print("\n===== 开始后缀搜索模式 [词根 字母] =====\n")
            # 按首字母分组并处理查询
            for first_char in [ord(c) for c in first_chars]:
                # 为当前字母生成所有查询
                current_letter_queries = []
                
                # 添加单字母查询
                single_letter_query = f"{root_word} {chr(first_char)}"
                current_letter_queries.append(single_letter_query)
                
                # 添加双字母和空格版本
                for second_char in [ord(c) for c in second_chars]:
                    compact_query = f"{root_word} {chr(first_char)}{chr(second_char)}"
                    spaced_query = f"{root_word} {chr(first_char)} {chr(second_char)}"
                    current_letter_queries.append(compact_query)
                    current_letter_queries.append(spaced_query)
                
                # 添加数字组合
                for num in numbers:
                    compact_query = f"{root_word} {chr(first_char)}{num}"
                    spaced_query = f"{root_word} {chr(first_char)} {num}"
                    current_letter_queries.append(compact_query)
                    current_letter_queries.append(spaced_query)
                
                # 处理当前字母的所有查询
                print(f"===== 开始处理字母 '{chr(first_char)}' 的查询 =====")
                
                # 每次处理新字母时强制刷新页面
                driver.get("https://www.google.com/")
                time.sleep(2)  # 等待页面加载
                
                previous_query = None
                for query in current_letter_queries:
                    if query in processed_queries:
                        print(f"跳过已处理的查询: {query}")
                        previous_query = query  # 即使跳过也更新上一次查询
                        continue  # 跳过已处理的查询

                    print(f"正在获取: {query}")
                    suggestions = get_google_suggestions(driver, query, previous_query, create_driver_func=driver_factory)
                    previous_query = query  # 更新上一次查询
                    query_count += 1  # 递增查询计数器
                    
                    # === 关键修改：无论是否有建议，都记录为已处理 ===
                    processed_queries.add(query)  # 记录已处理的查询
                    save_progress(processed_queries, progress_file)  # 保存进度
                    
                    if suggestions:  # 只处理有建议的情况
                        # 过滤掉已保存的建议和不相关的建议
                        new_suggestions = []
                        filtered_no_root = 0  # 记录因不相关而被过滤的数量
                        
                        # 判断词根是否包含多个词
                        root_words = root_word.lower().split()
                        is_multi_word_root = len(root_words) > 1
                        
                        for suggestion in suggestions:
                            # 跳过空建议和重复建议
                            if not suggestion or suggestion in saved_suggestions:
                                continue
                                
                            suggestion_lower = suggestion.lower()
                            
                            # 根据词根类型选择匹配策略
                            if is_multi_word_root:
                                # 多词词根：如果包含任意一个词根词，则认为相关
                                is_relevant = any(word in suggestion_lower for word in root_words)
                            else:
                                # 单词词根：要求完全包含词根
                                is_relevant = root_word.lower() in suggestion_lower
                            
                            if is_relevant:
                                new_suggestions.append(suggestion)
                                saved_suggestions.add(suggestion)
                            else:
                                filtered_no_root += 1
                                print(f"  过滤不相关的建议: '{suggestion}'，不包含词根词")
                        
                        # 只有有有效建议时才添加到批量保存列表
                        if new_suggestions:
                            batch_suggestions.extend(new_suggestions)
                    
                    # === 空结果检测逻辑保持不变 ===
                    if not suggestions or not any(new_suggestions if 'new_suggestions' in locals() else []):
                        pattern_key = query.split()[0]  # 使用模式的首字母作为键
                        empty_results_count[pattern_key] = empty_results_count.get(pattern_key, 0) + 1
                        
                        # 如果同一模式连续3次没有结果，考虑跳过该模式下的其他查询
                        if empty_results_count[pattern_key] >= 3:
                            print(f"检测到模式 '{pattern_key}' 多次无结果，跳过剩余查询")
                            # 跳过此模式下剩余的查询
                            break
                    
                    # 然后处理自适应等待逻辑
                    if suggestions:
                        consecutive_successes += 1
                        # 成功多次后逐渐减少等待时间
                        if consecutive_successes > 3:
                            wait_multiplier = max(0.5, wait_multiplier - 0.1)
                    else:
                        consecutive_successes = 0
                        wait_multiplier = 1.0  # 失败后恢复正常等待

                    # 使用自适应等待时间
                    wait_time = random.uniform(1, 3) * wait_multiplier
                    print(f"等待 {wait_time:.2f} 秒...")
                    time.sleep(wait_time)

                    # 每处理10个查询后批量保存
                    if len(batch_suggestions) >= 10 or query_count % 10 == 0:
                        with open(output_file, 'a', encoding='utf-8') as f:
                            for suggestion in batch_suggestions:
                                f.write(suggestion + '\n')
                        print(f"批量保存了 {len(batch_suggestions)} 条建议")
                        batch_suggestions = []
            suffix_end = time.time()
            print(f"后缀搜索耗时：{suffix_end - suffix_start:.2f} 秒")

        # 前缀搜索
        if do_prefix_search:
            prefix_start = time.time()
            print("\n===== 开始前缀搜索模式 [字母 词根] =====\n")
            
            # 首先一次性刷新页面
            driver.get("https://www.google.com/")
            time.sleep(2)  # 等待页面加载
            
            # 将查询按照模式分组
            single_letter_queries = []  # "a word"
            double_letter_queries = []  # "ab word"
            double_spaced_queries = []  # "a b word"
            number_queries = []  # "a0 word"
            
            # 按首字母分组进行前缀查询
            for first_char in [ord(c) for c in first_chars]:
                # 为当前字母生成所有前缀查询
                current_letter_queries = []
                
                # 添加单字母前缀查询
                single_letter_query = f"{chr(first_char)} {root_word}"
                current_letter_queries.append(single_letter_query)
                
                # 添加双字母和空格版本前缀
                for second_char in [ord(c) for c in second_chars]:
                    compact_query = f"{chr(first_char)}{chr(second_char)} {root_word}"
                    spaced_query = f"{chr(first_char)} {chr(second_char)} {root_word}"
                    current_letter_queries.append(compact_query)
                    current_letter_queries.append(spaced_query)
                
                # 添加数字组合前缀
                for num in numbers:
                    compact_query = f"{chr(first_char)}{num} {root_word}"
                    spaced_query = f"{chr(first_char)} {num} {root_word}"
                    current_letter_queries.append(compact_query)
                    current_letter_queries.append(spaced_query)
                
                # 处理当前字母的所有前缀查询
                print(f"===== 开始处理前缀字母 '{chr(first_char)}' 的查询 =====")
                
                # 每个字母的所有查询按模式分为4组
                query_patterns = [
                    [q for q in current_letter_queries if len(q.split()[0]) == 1],  # 单字母: "a word"
                    [q for q in current_letter_queries if len(q.split()[0]) == 2 and " " not in q.split()[0]],  # 双字母: "ab word"
                    [q for q in current_letter_queries if " " in q.split()[0]],  # 带空格: "a b word"
                    [q for q in current_letter_queries if any(c.isdigit() for c in q.split()[0])]  # 带数字: "a0 word"
                ]
                
                for pattern_group in query_patterns:
                    if not pattern_group:
                        continue
                        
                    # 每组开始时刷新一次页面，减少刷新频率
                    driver.get("https://www.google.com/")
                    time.sleep(random.uniform(1.5, 2.5))
                    
                    # 清空搜索框并输入第一个查询
                    search_box = WebDriverWait(driver, 10).until(
                        EC.visibility_of_element_located((By.NAME, "q"))
                    )
                    first_query = pattern_group[0]
                    search_box.clear()
                    
                    # 批量输入整个查询
                    search_box.send_keys(first_query)
                    time.sleep(0.5)  # 固定等待时间
                    
                    previous_query = first_query
                    suggestions = get_google_suggestions(driver, first_query, None, create_driver_func=driver_factory)
                    
                    # 第一次查询的建议处理
                    if suggestions:  # 只有当成功获取到建议时才保存和记录进度
                        # 过滤掉已保存的建议和不相关的建议
                        new_suggestions = []
                        filtered_no_root = 0  # 记录因不相关而被过滤的数量
                        
                        # 判断词根是否包含多个词
                        root_words = root_word.lower().split()
                        is_multi_word_root = len(root_words) > 1
                        
                        for suggestion in suggestions:
                            # 跳过空建议和重复建议
                            if not suggestion or suggestion in saved_suggestions:
                                continue
                                
                            suggestion_lower = suggestion.lower()
                            
                            # 根据词根类型选择匹配策略
                            if is_multi_word_root:
                                # 多词词根：如果包含任意一个词根词，则认为相关
                                is_relevant = any(word in suggestion_lower for word in root_words)
                            else:
                                # 单词词根：要求完全包含词根
                                is_relevant = root_word.lower() in suggestion_lower
                            
                            if is_relevant:
                                new_suggestions.append(suggestion)
                                saved_suggestions.add(suggestion)
                            else:
                                filtered_no_root += 1
                                print(f"  过滤不相关的建议: '{suggestion}'，不包含词根词")
                        
                        # 只写入新的有效建议
                        if new_suggestions:
                            # 收集建议
                            batch_suggestions.extend(new_suggestions)
                            processed_queries.add(first_query)
                            save_progress(processed_queries, progress_file)
                            
                            # 处理完一组查询后
                            if not any(new_suggestions):
                                pattern_key = pattern_group[0][0]  # 使用模式的首字母作为键
                                empty_results_count[pattern_key] = empty_results_count.get(pattern_key, 0) + 1
                                
                                # 如果同一模式连续3次没有结果，考虑跳过该模式下的其他查询
                                if empty_results_count[pattern_key] >= 3:
                                    print(f"检测到模式 '{pattern_key}' 多次无结果，跳过剩余查询")
                                    # 跳过此模式下剩余的查询
                                    break
                    
                    # 处理同一组中的其余查询
                    for query in pattern_group[1:]:
                        if query in processed_queries:
                            print(f"跳过已处理的查询: {query}")
                            previous_query = query  # 即使跳过也更新上一次查询
                            continue  # 跳过已处理的查询
                            
                        print(f"正在获取: {query}")
                        
                        # 对于同一模式下的查询，尝试清空并完全重新输入
                        search_box = driver.find_element(By.NAME, "q")
                        search_box.clear()
                        time.sleep(0.2)
                        
                        # 批量输入整个查询
                        search_box.send_query = query
                        time.sleep(0.5)  # 固定等待时间
                        
                        suggestions = get_google_suggestions(driver, query, None, create_driver_func=driver_factory)
                        previous_query = query
                        
                        # === 关键修改：无论是否有建议，都记录为已处理 ===
                        processed_queries.add(query)
                        save_progress(processed_queries, progress_file)
                        
                        if suggestions:  # 只处理有建议的情况
                            # 过滤逻辑与上面相同
                            new_suggestions = []
                            filtered_no_root = 0
                            
                            # 判断词根是否包含多个词
                            root_words = root_word.lower().split()
                            is_multi_word_root = len(root_words) > 1
                            
                            for suggestion in suggestions:
                                # 跳过空建议和重复建议
                                if not suggestion or suggestion in saved_suggestions:
                                    continue
                                    
                                suggestion_lower = suggestion.lower()
                                
                                # 根据词根类型选择匹配策略
                                if is_multi_word_root:
                                    # 多词词根：如果包含任意一个词根词，则认为相关
                                    is_relevant = any(word in suggestion_lower for word in root_words)
                                else:
                                    # 单词词根：要求完全包含词根
                                    is_relevant = root_word.lower() in suggestion_lower
                                
                                if is_relevant:
                                    new_suggestions.append(suggestion)
                                    saved_suggestions.add(suggestion)
                                else:
                                    filtered_no_root += 1
                                    print(f"  过滤不相关的建议: '{suggestion}'，不包含词根词")
                            
                            # 只有有有效建议时才添加到批量保存列表
                            if new_suggestions:
                                batch_suggestions.extend(new_suggestions)
                        
                        # === 空结果检测逻辑保持不变 ===
                        if not suggestions or not any(new_suggestions if 'new_suggestions' in locals() else []):
                            pattern_key = query.split()[0]  # 使用模式的首字母作为键
                            empty_results_count[pattern_key] = empty_results_count.get(pattern_key, 0) + 1
                            
                            if empty_results_count[pattern_key] >= 3:
                                print(f"检测到模式 '{pattern_key}' 多次无结果，跳过剩余查询")
                                break
                    
                    # 然后处理自适应等待逻辑
                    if suggestions:
                        consecutive_successes += 1
                        # 成功多次后逐渐减少等待时间
                        if consecutive_successes > 3:
                            wait_multiplier = max(0.5, wait_multiplier - 0.1)
                    else:
                        consecutive_successes = 0
                        wait_multiplier = 1.0  # 失败后恢复正常等待

                    # 使用自适应等待时间
                    wait_time = random.uniform(1, 3) * wait_multiplier
                    print(f"等待 {wait_time:.2f} 秒...")
                    time.sleep(wait_time)

                    # 对查询进行排序
                    pattern_group.sort(key=get_query_priority, reverse=True)
            prefix_end = time.time()
            print(f"前缀搜索耗时：{prefix_end - prefix_start:.2f} 秒")

    except KeyboardInterrupt:
        print("程序被中断，正在保存进度...")
        save_progress(processed_queries, progress_file)  # 保存进度
        print("进度已保存，程序退出。")
    finally:
        driver.quit()  # 关闭浏览器
        # 播放完成提示音（更通用的方式，适用于 Windows）
        try:
            import winsound  # 导入Windows系统声音模块
            for _ in range(10):
                winsound.MessageBeep()  # 播放系统提示音
                time.sleep(0.3)
        except ImportError:
            # 如果不是Windows系统，仍然尝试用print("\a")
            for _ in range(10):
                print("\a")  # 系统蜂鸣声
                time.sleep(0.3)
        print("===== 程序已完成！=====")
        end_time = time.time()    # 记录结束时间
        print(f"程序总运行时间：{end_time - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
