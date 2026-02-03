import os
import argparse

def find_folders_without_gcov_files(directory):
    total_dirs = 0
    with_gcov = 0
    without_gcov = 0

    # 只检查一级目录下的文件夹
    for folder_name in os.listdir(directory):
        folder_path = os.path.join(directory, folder_name)

        # 只处理文件夹
        if os.path.isdir(folder_path):
            total_dirs += 1
            files = os.listdir(folder_path)

            if any(file.endswith('.c.gcov') for file in files):
                with_gcov += 1
            else:
                without_gcov += 1
                print(f"文件夹 {folder_path} 不包含 *.c.gcov 文件")

    # 统计信息输出
    print("\n========== 统计结果 ==========")
    print(f"一级子文件夹总数: {total_dirs}")
    print(f"包含 *.c.gcov 文件的文件夹数: {with_gcov}")
    print(f"不包含 *.c.gcov 文件的文件夹数: {without_gcov}")

def main():
    parser = argparse.ArgumentParser(
        description="列出不包含 *.c.gcov 文件的一级子文件夹，并统计数量"
    )
    parser.add_argument('directory', help="需要检查的目录路径")
    args = parser.parse_args()

    find_folders_without_gcov_files(args.directory)

if __name__ == "__main__":
    main()