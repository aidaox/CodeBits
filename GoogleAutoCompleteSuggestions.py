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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import json
import os

def get_google_suggestions(driver, query):
    """
    使用Selenium获取谷歌搜索下拉列表的关键词
    :param driver: Selenium WebDriver实例
    :param query: 用户输入的查询字符串
    :return: 返回下拉列表的关键词
    """
    driver.get("https://www.google.com/")
    
    # 使用显式等待，直到搜索框可见
    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.NAME, "q"))
        )
    except Exception as e:
        print(f"等待搜索框时出错: {e}")
        return []  # 返回空列表以避免后续错误

    search_box = driver.find_element(By.NAME, "q")
    search_box.clear()  # 清空搜索框
    search_box.send_keys(query)

    # 使用显式等待，直到下拉建议可见
    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "div.OBMEnb ul.G43f7e"))
        )
    except Exception as e:
        print(f"等待下拉建议时出错: {e}")
        return []  # 返回空列表以避免后续错误

    # 获取下拉建议
    suggestions = driver.find_elements(By.CSS_SELECTOR, "div.OBMEnb ul.G43f7e li")  # 使用CSS选择器
    results = [suggestion.text for suggestion in suggestions]

    # 打印获取到的建议
    print(f"获取到的建议: {results}")  # 打印获取到的建议
    return results

def save_suggestions_to_file(suggestions, filename):
    """
    将建议保存到本地文件
    :param suggestions: 要保存的建议列表
    :param filename: 文件名
    """
    with open(filename, 'a', encoding='utf-8') as f:  # 以追加模式打开文件
        for suggestion in suggestions:
            f.write(suggestion + '\n')  # 每个建议写入一行

def load_progress(filename):
    """
    从文件中加载进度
    :param filename: 进度文件名
    :return: 已处理的查询列表
    """
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_progress(queries, filename):
    """
    保存当前进度到文件
    :param queries: 当前已处理的查询列表
    :param filename: 进度文件名
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(queries, f)

def main():
    # 弹出交互窗口让用户输入需要搜索的词根
    root_word = input("请输入需要搜索的词根: ").strip()  # 去除前后空格
    if not root_word:
        print("词根不能为空，请重新运行程序。")
        return

    options = webdriver.ChromeOptions()
    options.add_argument("--lang=en")  # 设置浏览器语言为英文
    driver = webdriver.Chrome(options=options)  # 只需打开一次浏览器

    progress_file = f'{root_word}_progress.json'  # 进度文件名
    processed_queries = load_progress(progress_file)  # 加载已处理的查询

    # 生成查询字符串
    all_queries = []
    for first_char in range(97, 123):  # a-z
        for second_char in range(97, 123):  # a-z
            all_queries.append(f"{root_word} {chr(first_char)}{chr(second_char)}")  # 词根 + aa - zz
        for num in range(10):  # 0-9
            all_queries.append(f"{root_word} {chr(first_char)}{num}")  # 词根 + a0 - z9

    # 将文件名中的空格替换为下划线
    safe_root_word = root_word.replace(" ", "_")  # 用于文件名的安全词根

    try:
        for query in all_queries:
            if query in processed_queries:
                continue  # 跳过已处理的查询

            print(f"正在获取: {query}")
            suggestions = get_google_suggestions(driver, query)
            save_suggestions_to_file(suggestions, f'{safe_root_word}.txt')  # 保存到以词根命名的文件

            processed_queries.append(query)  # 记录已处理的查询
            save_progress(processed_queries, progress_file)  # 保存进度

            # 添加随机等待时间
            time.sleep(random.uniform(2, 5))  # 随机等待2到5秒

    except KeyboardInterrupt:
        print("程序被中断，正在保存进度...")
        save_progress(processed_queries, progress_file)  # 保存进度
        print("进度已保存，程序退出。")
    finally:
        driver.quit()  # 关闭浏览器

if __name__ == "__main__":
    main()
