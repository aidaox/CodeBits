"""
batch_translate.py

功能：
该脚本用于批量翻译一种语言单词到另一种语言，支持多线程和多进程翻译。用户可以通过命令行参数指定输入文件、源语言、目标语言、线程数和每批处理的单词数。

使用方法：
1. 确保已安装所需的库：
   - pandas
   - argostranslate
   - tqdm

2. 在命令行中运行脚本：
   python batch_translate.py <输入文件路径> [--from_lang <源语言代码>] [--to_lang <目标语言代码>] [--threads <线程数>] [--batch_size <每批处理的单词数>] [--use_mp]

   示例：
   python batch_translate.py words.txt --from_lang en --to_lang zh --threads 4 --batch_size 20 --use_mp

参数说明：
- <输入文件路径>：包含待翻译单词的文本文件路径。
- --from_lang：源语言代码，默认为 'en'（英语）。
- --to_lang：目标语言代码，默认为 'zh'（中文）。
- --threads：使用的线程数，默认为 4。
- --batch_size：每批处理的单词数，默认为 20。
- --use_mp：使用多进程而非多线程。

注意：在运行之前，请确保已在系统中安装了 Argos Translate 的相关翻译包。
"""
import pandas as pd
import argostranslate.package
import argostranslate.translate
import os
import sys
import time
import threading
import queue
import argparse
from pathlib import Path
from tqdm import tqdm
import multiprocessing as mp

# 设置环境变量以启用 GPU 加速（如果可用）
os.environ["ARGOS_DEVICE_TYPE"] = "cuda"  # 强制使用CUDA，确保确实尝试GPU

# 检查GPU状态
def check_gpu_status():
    print("\n===== GPU状态检查 =====")
    try:
        import torch
        print(f"PyTorch版本: {torch.__version__}")
        print(f"CUDA是否可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA设备数量: {torch.cuda.device_count()}")
            print(f"当前CUDA设备: {torch.cuda.get_device_name(0)}")
            print(f"当前CUDA内存使用: {torch.cuda.memory_allocated(0)/1024**2:.2f} MB")
    except ImportError:
        print("未安装PyTorch，无法检查GPU状态")
    
    # 检查argostranslate的设备状态
    print(f"Argos Translate设置的设备类型: {os.environ.get('ARGOS_DEVICE_TYPE', '未设置')}")
    
    # 尝试检查系统GPU信息
    if os.name == 'nt':  # Windows系统
        try:
            import subprocess
            gpu_info = subprocess.check_output('nvidia-smi', shell=True).decode('utf-8')
            print("GPU信息:")
            print(gpu_info)
        except:
            print("无法获取GPU信息，可能未安装NVIDIA显卡或驱动")
    print("========================\n")

# 解析命令行参数
def parse_arguments():
    parser = argparse.ArgumentParser(description='批量翻译英文单词到中文')
    parser.add_argument('input_file', type=str, help='输入文件路径')
    parser.add_argument('--from_lang', type=str, default='en', help='源语言代码 (默认: en)')
    parser.add_argument('--to_lang', type=str, default='zh', help='目标语言代码 (默认: zh)')
    parser.add_argument('--threads', type=int, default=4, help='翻译进程/线程数 (默认: 4)')
    parser.add_argument('--batch_size', type=int, default=20, help='每批处理的单词数 (默认: 20)')
    parser.add_argument('--use_mp', action='store_true', help='使用多进程而非多线程')
    return parser.parse_args()

# 下载并安装 Argos Translate 包（如果尚未安装）
def install_translation_package(from_code, to_code):
    print(f"正在检查 {from_code} 到 {to_code} 的翻译包...")
    
    # 检查是否已安装该语言包
    installed_packages = argostranslate.package.get_installed_packages()
    for package in installed_packages:
        if package.from_code == from_code and package.to_code == to_code:
            print(f"已安装 {from_code} 到 {to_code} 的翻译包")
            return
    
    # 如果未安装，则下载并安装
    print(f"未找到 {from_code} 到 {to_code} 的翻译包，正在下载...")
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    
    try:
        package_to_install = next(
            filter(lambda x: x.from_code == from_code and x.to_code == to_code, available_packages)
        )
        print(f"正在安装 {from_code} 到 {to_code} 的翻译包...")
        argostranslate.package.install_from_path(package_to_install.download())
        print(f"安装完成！")
    except StopIteration:
        print(f"错误：找不到从 {from_code} 到 {to_code} 的翻译包")
        sys.exit(1)

# 批量翻译工作线程函数
def translate_worker(work_queue, result_dict, from_lang, to_lang, batch_size=10):
    while True:
        try:
            # 尝试获取一批单词
            batch = []
            for _ in range(batch_size):
                try:
                    word = work_queue.get(block=False)
                    if word is None:  # 结束信号
                        # 把None放回队列，让其他线程也能收到结束信号
                        work_queue.put(None)
                        if batch:  # 处理已获取的批次
                            break
                        else:  # 没有要处理的单词了
                            return
                    batch.append(word)
                except queue.Empty:
                    break
            
            if not batch:
                break
                
            # 批量翻译：拼接所有单词，用特殊分隔符分开
            batch_text = "\n\n---SPLIT---\n\n".join(batch)
            try:
                # 使用Argos Translate进行批量翻译
                translated_text = argostranslate.translate.translate(batch_text, from_lang, to_lang)
                
                # 拆分结果
                translated_parts = translated_text.split("\n\n---SPLIT---\n\n")
                
                # 确保结果数量与原文匹配
                if len(translated_parts) == len(batch):
                    for i, word in enumerate(batch):
                        result_dict[word] = translated_parts[i]
                else:
                    # 回退到逐个翻译
                    for word in batch:
                        result_dict[word] = argostranslate.translate.translate(word, from_lang, to_lang)
            except Exception as e:
                print(f"批量翻译时出错: {str(e)}，回退到单词翻译模式")
                # 回退到逐个翻译
                for word in batch:
                    try:
                        result_dict[word] = argostranslate.translate.translate(word, from_lang, to_lang)
                    except Exception as e:
                        print(f"翻译 '{word}' 时出错: {str(e)}")
                        result_dict[word] = f"ERROR: {str(e)}"
            
            # 标记所有任务完成
            for _ in batch:
                work_queue.task_done()
                
        except Exception as e:
            print(f"线程处理时出错: {str(e)}")
            break

# 进程池翻译函数
def translate_batch(batch, from_lang, to_lang):
    result = {}
    # 批量翻译：拼接所有单词，用特殊分隔符分开
    batch_text = "\n\n---SPLIT---\n\n".join(batch)
    try:
        # 使用Argos Translate进行批量翻译
        translated_text = argostranslate.translate.translate(batch_text, from_lang, to_lang)
        
        # 拆分结果
        translated_parts = translated_text.split("\n\n---SPLIT---\n\n")
        
        # 确保结果数量与原文匹配
        if len(translated_parts) == len(batch):
            for i, word in enumerate(batch):
                result[word] = translated_parts[i]
        else:
            # 回退到逐个翻译
            for word in batch:
                result[word] = argostranslate.translate.translate(word, from_lang, to_lang)
    except Exception as e:
        print(f"批量翻译时出错: {str(e)}，回退到单词翻译模式")
        # 回退到逐个翻译
        for word in batch:
            try:
                result[word] = argostranslate.translate.translate(word, from_lang, to_lang)
            except Exception as e:
                print(f"翻译 '{word}' 时出错: {str(e)}")
                result[word] = f"ERROR: {str(e)}"
    return result

# 主函数
def main():
    # 解析命令行参数
    args = parse_arguments()
    
    # 检查GPU状态
    check_gpu_status()
    
    # 获取输入文件和输出文件名
    input_file = args.input_file if hasattr(args, 'input_file') else sys.argv[1]
    input_path = Path(input_file)
    output_file = f"translated_{input_path.stem}_{args.from_lang}_to_{args.to_lang}.csv"
    
    # 检查并安装翻译包
    install_translation_package(args.from_lang, args.to_lang)
    
    # 读取英文单词文件
    try:
        with open(input_file, 'r', encoding='utf-8') as file:
            words = file.readlines()
        
        # 去除换行符和空白行
        words = [word.strip() for word in words if word.strip()]
        print(f"从 {input_file} 读取了 {len(words)} 个单词")
    except Exception as e:
        print(f"读取输入文件时出错: {str(e)}")
        sys.exit(1)
    
    # 检查是否存在已翻译的结果文件
    existing_translations = {}
    if os.path.exists(output_file):
        try:
            # 读取已翻译的结果
            df_existing = pd.read_csv(output_file)
            existing_translations = dict(zip(df_existing['原文'], df_existing['翻译']))
            print(f"从 {output_file} 读取了 {len(existing_translations)} 个已翻译的单词")
        except Exception as e:
            print(f"读取已有翻译文件时出错: {str(e)}")
            print("将创建新的翻译文件")
    
    # 找出未翻译的单词
    remaining_words = [word for word in words if word not in existing_translations]
    print(f"需要翻译的单词数: {len(remaining_words)}")
    
    if not remaining_words:
        print("所有单词已翻译完成！")
        return
    
    # 结果字典
    result_dict = {}
    
    # 选择使用多进程或多线程
    start_time = time.time()
    
    if args.use_mp:
        # 使用多进程
        print(f"使用多进程模式，进程数: {args.threads}")
        
        # 分割任务
        batch_size = max(1, min(args.batch_size, len(remaining_words) // (args.threads * 2) + 1))
        batches = [remaining_words[i:i+batch_size] for i in range(0, len(remaining_words), batch_size)]
        
        print(f"分割为 {len(batches)} 个批次，每批约 {batch_size} 个单词")
        
        # 创建进程池
        with mp.Pool(processes=args.threads) as pool:
            # 创建并跟踪异步任务
            tasks = []
            for batch in batches:
                task = pool.apply_async(translate_batch, (batch, args.from_lang, args.to_lang))
                tasks.append(task)
            
            # 显示进度条
            with tqdm(total=len(batches), desc="批次进度") as pbar:
                completed = 0
                while completed < len(batches):
                    new_completed = sum(1 for task in tasks if task.ready())
                    if new_completed > completed:
                        pbar.update(new_completed - completed)
                        completed = new_completed
                    time.sleep(0.1)
            
            # 获取所有结果
            for task in tasks:
                batch_results = task.get()
                result_dict.update(batch_results)
    else:
        # 使用多线程
        print(f"使用多线程模式，线程数: {args.threads}")
        
        # 创建工作队列
        work_queue = queue.Queue()
        
        # 将未翻译的单词添加到工作队列
        for word in remaining_words:
            work_queue.put(word)
        
        # 创建并启动工作线程
        threads = []
        for _ in range(min(args.threads, len(remaining_words))):
            thread = threading.Thread(
                target=translate_worker, 
                args=(work_queue, result_dict, args.from_lang, args.to_lang, args.batch_size)
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # 显示进度条
        with tqdm(total=len(remaining_words), desc="翻译进度") as pbar:
            last_done = 0
            while work_queue.unfinished_tasks > 0:
                current_done = len(remaining_words) - work_queue.unfinished_tasks
                if current_done > last_done:
                    pbar.update(current_done - last_done)
                    last_done = current_done
                time.sleep(0.1)
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
    
    # 计算翻译速度
    translation_time = time.time() - start_time
    words_per_second = len(result_dict) / translation_time if translation_time > 0 else 0
    print(f"\n翻译完成! 用时: {translation_time:.2f}秒, 速度: {words_per_second:.2f}词/秒")
    
    # 合并已翻译的结果和新翻译的结果
    all_translations = existing_translations.copy()
    all_translations.update(result_dict)
    
    # 创建 DataFrame，保持原始单词顺序
    data = []
    for word in words:
        if word in all_translations:
            data.append((word, all_translations[word]))
    
    df = pd.DataFrame(data, columns=['原文', '翻译'])
    
    # 保存为 CSV 文件
    try:
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"翻译完成，已保存为 {output_file}")
    except Exception as e:
        print(f"保存翻译结果时出错: {str(e)}")
        
        # 尝试保存到备份文件
        backup_file = f"backup_{output_file}"
        try:
            df.to_csv(backup_file, index=False, encoding='utf-8-sig')
            print(f"已保存备份文件: {backup_file}")
        except:
            print("无法保存备份文件，请检查磁盘空间和权限")

if __name__ == "__main__":
    main()
