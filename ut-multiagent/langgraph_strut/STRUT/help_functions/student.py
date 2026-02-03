import requests
import json
import csv

def crawl_dynamic_performance_data():
    # ---------------------- 第一步：定位目标数据接口 ----------------------
    print('开始爬取数据')
    target_url = "https://search.damai.cn/searchajax.html?keyword=&cty=&ctl=&sctl=&tsg=0&st=&et=&order=1&pageSize=30&currPage=1&tn="  # 替换为你的演出数据接口URL

    # ---------------------- 第二步：构造请求头 ----------------------
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
        "Cookie": "cna=yhSfIWx1EzwCASRwA3KAfSAs; xlly_s=1; isg=BKeni4XKgqaQLwYqT4-5H1j_NttxLHsOQj2pEHkUBDbSaMYqgf2tXslrj2h20lOG; tfstk=ge7xLSsPp82cNCDqMOqujA-TtpFu-uf22t5ISdvmfTBR19F2s-7G2CBGeS5c1-SOe16LgC2VSghOTTB9bSJMCdBG1iVu-yfVgF81BJ43-aTz3v_vCAY6uUTWdkbz-yfVGF8_KJ4hmjbohC965nt6Fz9y_C91CdT7wCOihcgfC_NJUBmsGdOjP4O6MF91CFNRNLR65I6657CWUCMZsupZcp0O0qv4UWgmN5N1yIKvdVv-WVFMMnpCGLhK9aU6Dp1XeVwAv3l6BL7QEuCP0i6DaOULeesFeNKBWrHeMg1pPKYQWfJkXaBAX3GIRn5lk1I6VXV9zhO9AFt-1V1JzLBdleaIeQS5iG_VHf36gZbHXp-81V-MPwxCAthaT_TX1O-FSJu2h11F8MYLkvRAV6LR47bhJkqSKpdic7F-bc-Xa-xq3sKBQCF6wpVkicow2uRJK7F-bc-XaQp3ZxmZb3EP.; XSRF-TOKEN=a38a1438-6dc9-413f-93eb-c05b32fbc3bf",  # 替换为你的真实Cookie（若接口需要登录验证）
        "Referer": "https://search.damai.cn/search.htm?spm=a2oeg.search_category.top.dcategory.19e24d15e7aNQt&order1"  # 替换为接口对应的网页地址（增强请求真实性）
    }

    try:
        # ---------------------- 第三步：模拟发送接口请求，获取JSON数据----------------------
        print('开始发送请求')
        response = requests.get(
            url=target_url,
            headers=headers,
            timeout=20)

        # 验证请求是否成功（状态码200表示成功）
        response.raise_for_status()  # 若状态码非200，直接抛出异常

        # ---------------------- 第四步：解析JSON数据，提取所需信息 ----------------------
        # 将响应内容转为Python字典（无需解析HTML，直接操作数据）
        performance_data = response.json()
        
        # 提取演出信息
        # 先打印原始JSON，方便查看真实结构（调试时用，后续可删除）
        print("接口返回的原始JSON数据：")
        print(json.dumps(performance_data, ensure_ascii=False, indent=2))


        if 'resultData' in performance_data:  # 判断接口返回是否正常
            print('状态正常')
            
            performance_list = performance_data["resultData"][:3]  # 提取演出列表
            extracted_info = []  # 存储提取后的关键信息
            print('提取的演出列表:',performance_list)
            for performance in performance_list:
                # 提取每个演出的核心字段
                info = {
                    "演出名称": performance.get("name", "未知名称"),  # get方法避免键不存在报错
                    "演出时间": performance.get("showtime", "未知时间"),
                    "演出地点": performance.get("cityname", "未知地点"),
                    "票价区间": performance.get("price_str", "未知票价"),
                    "演出状态": performance.get("showstatus", "无状态")
                }
                extracted_info.append(info)
            print("o", end="", flush=True)

            # ---------------------- 第五步：保存数据 ----------------------
            csv_filename='大麦演出信息收集.csv'
            if extracted_info:
                headers_csv=extracted_info[0].keys()
                with open(csv_filename, "w", encoding="utf-8-sig",newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=headers_csv)
                    writer.writeheader()
                    writer.writerows(extracted_info)

            print(f"\n爬取成功！共获取{len(extracted_info)}条演出信息，已保存到「大麦演出信息收集.csv」")
            return extracted_info
        else:
            print('接口数据异常')
        

    # 捕获可能出现的异常（网络错误、超时、JSON解析失败等）
    except requests.exceptions.RequestException as e:
        print(f"请求失败：{str(e)}")
    except json.JSONDecodeError:
        print("JSON解析失败，该接口返回的不是JSON数据")
    except KeyError as e:
        print(f"数据提取失败，缺少关键键名：{str(e)}（请检查JSON结构是否匹配）")
    except Exception as e:
        print(f"未知错误：{str(e)}")

# 执行爬取函数
if __name__ == "__main__":
    crawl_dynamic_performance_data()