#!/usr/bin/env python3
"""
处理JSONL文件，将每行数据改写成3种形式：
1. 原形式
2. 将image_path改为空
3. 将llm_input_renamed加到llm_output_renamed前（中间加上一个空格），并将llm_input_renamed改为空

使用方法:
python process_jsonl.py input.jsonl output.jsonl --options 1 2 3
"""

import json
import argparse
import copy
from pathlib import Path


def process_line(line_data):
    """
    处理单行数据，返回3种形式
    
    Args:
        line_data: 原始数据字典
        
    Returns:
        list: 包含3种形式的列表
    """
    # 形式1: 原形式
    form1 = copy.deepcopy(line_data)
    
    # 形式2: 将image_path改为空
    form2 = copy.deepcopy(line_data)
    if 'image_path' in form2:
        form2['image_path'] = []
    
    # 形式3: 将llm_input_renamed加到llm_output_renamed前，并将llm_input_renamed改为空
    form3 = copy.deepcopy(line_data)
    if 'llm_input_renamed' in form3 and 'llm_output_renamed' in form3:
        # 将llm_input_renamed加到llm_output_renamed前面（中间加空格）
        form3['llm_output_renamed'] = form3['llm_input_renamed'] + " " + form3['llm_output_renamed']
        # 将llm_input_renamed改为空
        form3['llm_input_renamed'] = ""
    
    return [form1, form2, form3]


def main():
    parser = argparse.ArgumentParser(
        description='处理JSONL文件，将每行数据改写成3种形式并输出选定的形式'
    )
    parser.add_argument('input_file', type=str, help='输入JSONL文件路径')
    parser.add_argument('output_file', type=str, help='输出JSONL文件路径')
    parser.add_argument(
        '--options', 
        type=int, 
        nargs='+', 
        choices=[1, 2, 3],
        default=[1, 2, 3],
        help='保存选项：1=原形式, 2=image_path为空, 3=llm_input加到llm_output前且为空 (默认: 1 2 3)'
    )
    
    args = parser.parse_args()
    
    # 检查输入文件是否存在
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"错误: 输入文件 {args.input_file} 不存在")
        return
    
    # 确保输出目录存在
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 读取并处理文件
    processed_count = 0
    output_count = 0
    
    print(f"正在处理文件: {args.input_file}")
    print(f"保存选项: {sorted(args.options)}")
    
    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for line_num, line in enumerate(infile, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                # 解析JSON数据
                data = json.loads(line)
                
                # 处理成3种形式
                forms = process_line(data)
                
                # 根据选项写入输出文件
                for option in args.options:
                    form_data = forms[option - 1]  # option是1-3，索引是0-2
                    outfile.write(json.dumps(form_data, ensure_ascii=False) + '\n')
                    output_count += 1
                
                processed_count += 1
                
            except json.JSONDecodeError as e:
                print(f"警告: 第 {line_num} 行JSON解析失败: {e}")
            except Exception as e:
                print(f"警告: 第 {line_num} 行处理失败: {e}")
    
    print(f"\n处理完成!")
    print(f"- 输入行数: {processed_count}")
    print(f"- 输出行数: {output_count}")
    print(f"- 输出文件: {args.output_file}")


if __name__ == "__main__":
    main()
