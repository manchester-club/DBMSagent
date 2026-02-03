import re
import json  # <--- 新增导入
from util import determine_type


def make_case_list(data, has_stub: bool, default_PTR):
    """Constructing a list of test cases"""
    
    # <--- 修改开始：使用更灵活的正则表达式来匹配JSON对象 ---
    # 由于新增了很多字段，使用更简单的方法：匹配整个JSON对象
    pattern = re.compile(
        r'{\s*"desc":\s*"(?P<desc>[^"]+)"[^}]*}',
        re.DOTALL
    )
    # <--- 修改结束 ---

    matches = pattern.finditer(data)
    test_cases = []

    for match in matches:
        # 获取完整的JSON对象文本
        full_match_text = match.group(0)
        
        try:
            # 直接解析完整的JSON对象
            case_obj = json.loads(full_match_text)
            
            # 提取所有字段
            desc = case_obj.get('desc', '')
            inputs_list = case_obj.get('inputs', [])
            outputs_list = case_obj.get('outputs', [])
            direct_includes = case_obj.get('direct_includes', [])
            type_definitions = case_obj.get('type_definitions', {})
            macros = case_obj.get('macros', [])
            structs = case_obj.get('structs', [])
            file_globals = case_obj.get('file_globals', [])
            func_code = case_obj.get('func_code', '')
            userVar = case_obj.get('userVar', [])
            ios = case_obj.get('ios', [])
            stubins_list = case_obj.get('stubins', [])
            
            # 将inputs和outputs转换为字符串格式以兼容现有的解析逻辑
            inputs = json.dumps(inputs_list)
            outputs = json.dumps(outputs_list)
            stubins = json.dumps(stubins_list)
            
        except json.JSONDecodeError as e:
            print(f"警告：无法解析JSON对象：{e}")
            # 回退到原始的字段提取方法
            desc = match.group('desc')
            inputs = "[]"
            outputs = "[]"
            stubins = "[]"
            direct_includes = []
            type_definitions = {}
            macros = []
            structs = []
            file_globals = []
            func_code = ""
            userVar = []
            ios = []

        input_pattern = re.compile(
            r'{\s*"expr":\s*"(?P<expr>[^"]+)",\s*"value":\s*(?:'
            r'(?P<value_hex>"(0[xX][0-9a-fA-F]+)"|0[xX][0-9a-fA-F]+)|'
            r'(?P<value_float>-?\d+\.\d+)|'
            r'(?P<value_int>-?\d+)|'
            r'(?P<value_str>"[^"]+")|'
            r'\[\s*(?P<value_bracket>(?:-?\d+\.\d+|-?\d+|0[xX][0-9a-fA-F]+|"(0[xX][0-9a-fA-F]+)"|"[^"]+")\s*'
            r'(?:,\s*(?:-?\d+\.\d+|-?\d+|0[xX][0-9a-fA-F]+|"(0[xX][0-9a-fA-F]+)"|"[^"]+"))*)\s*\]'
            r')\s*}'
        )
        
        # ... (内部的 output_pattern 和 stub_pattern 保持不变) ...
        output_pattern = re.compile(
            r'{\s*"expr":\s*"(?P<expr>[^"]+)",'
            r'\s*"value":\s*(?:"(?P<value_str>[^"]+)"|(?P<value_hex>0[xX][0-9a-fA-F]+)|(?P<value_float>-?\d+\.\d+)|(?P<value_int>-?\d+))\s*}'
        )
        stub_list = []
        if has_stub and stubins: # 确保 stubins 非空
            stub_pattern = re.compile(
                r'{\s*"funcName":\s*"(?P<funcName>[^"]+)",\s*"expr":\s*"(?P<expr>[^"]+)",'
                r'\s*"value":\s*(?:(?P<value>\[\s*((?:(?:-?\d+\.\d+)|(?:-?\d+)|(?:"[^"]*")|(?:\'[^\']*\')|(?:0[xX][0-9a-fA-F]+))(\s*,\s*(?:(?:-?\d+\.\d+)|(?:-?\d+)|(?:"[^"]*")|(?:\'[^\']*\')|(?:0[xX][0-9a-fA-F]+)))*\s*)\]))\s*}'
            )
            stub_list = [m.groupdict() for m in stub_pattern.finditer(stubins)]


        # ... (后续的 input_list, output_list, bracket_list 等处理逻辑保持不变) ...
        input_list = [m.groupdict() for m in input_pattern.finditer(inputs)]
        output_list = [m.groupdict() for m in output_pattern.finditer(outputs)]

        bracket_list = []
        # process input value
        for item in input_list:
            if item['value_hex'] is not None:
                value_hex = item['value_hex']
                if value_hex.find('"') != -1:
                    value_hex = value_hex.replace('"', '')
                # temp = int(value_hex, 16)  # process hex number
                item['value'] = value_hex
            elif item['value_float'] is not None:
                item['value'] = float(item['value_float'])
            elif item['value_int'] is not None:
                item['value'] = int(item['value_int'])
            elif item['value_bracket'] is not None:
                '''array value'''
                expr = item['expr']
                bracket_value = item['value_bracket'].split(',')
                i = 0
                for value in bracket_value:
                    value = value.replace(' ', '')
                    # get array type
                    if determine_type(value) == 'Integer':
                        value = int(value)
                    elif determine_type(value) == 'Float':
                        value = float(value)
                    elif determine_type(value) == 'Hexadecimal':
                        if value.find('"') != -1:
                            value = value.replace('"', '')
                    inp = {'expr': expr + '[' + str(i) + ']', 'value': value}
                    bracket_list.append(inp)
                    i += 1
                item['value'] = 'delete'
            else:
                value_str = item['value_str']
                if value_str.find('"') != -1:
                    value_str = value_str.replace('"', '')
                item['value'] = value_str

            del item['value_str']
            del item['value_hex']
            del item['value_float']
            del item['value_int']
            del item['value_bracket']
        # delete data
        for i in range(len(input_list) - 1, -1, -1):
            if input_list[i]['value'] == 'delete':
                del input_list[i]
        for item in bracket_list:
            input_list.append(item)
        # convert type
        for item in output_list:
            if item['value_hex'] is not None:
                item['value'] = item['value_hex']  # 处理十六进制数
            elif item['value_float'] is not None:
                item['value'] = float(item['value_float'])
            elif item['value_int'] is not None:
                item['value'] = int(item['value_int'])
            else:
                item['value'] = item['value_str']
            del item['value_str']
            del item['value_hex']
            del item['value_float']
            del item['value_int']

        for item in stub_list:
            value: str = item['value']
            value = value.replace('[', '').replace(']', '').replace(',', ';')
            item['value'] = value
            # process function pointer
            for ite in default_PTR:
                if ite['expr'] == item['funcName']:
                    item['funcName'] = ite['userVar']


        # <--- 修改开始：将所有新解析出的字段添加到最终结果中 ---
        test_cases.append({
            "desc": desc,
            "inputs": input_list,
            "stubins": stub_list,
            "outputs": output_list,
            "direct_includes": direct_includes,
            "type_definitions": type_definitions,
            "macros": macros,
            "structs": structs,
            "file_globals": file_globals,
            "func_code": func_code,
            "userVar": userVar,
            "ios": ios,
            "doBoundary": 0,
            "ioins": [],
        })
        # <--- 修改结束 ---
    return test_cases