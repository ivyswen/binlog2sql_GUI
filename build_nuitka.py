import os
import sys
import subprocess
import shutil

def build_executable():
    """使用Nuitka构建可执行文件"""
    print("开始使用Nuitka构建可执行文件...")

    # 确保资源文件已编译
    print("编译资源文件...")
    try:
        subprocess.run(["pyside6-rcc", "resources.qrc", "-o", "resources_rc.py"], check=True)
        print("资源文件编译成功")
    except Exception as e:
        print(f"资源文件编译失败: {e}")
        sys.exit(1)

    # 创建输出目录
    output_dir = "nuitka_build"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 使用Nuitka构建可执行文件
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",                # 创建独立的可执行文件
        "--windows-console-mode=disable",     # 禁用控制台窗口
        "--windows-icon-from-ico=Resources/favicon.ico",  # 设置应用程序图标
        "--include-data-dir=Resources=Resources",    # 包含资源目录
        # "--include-data-file=resources_rc.py=resources_rc.py",  # 包含资源文件
        "--output-dir=" + output_dir,  # 输出目录
        "--company-name=chaji",        # 公司名称
        "--product-name=binlog2sql",        # 产品名称
        "--file-version=1.0.0",        # 文件版本
        "--product-version=1.0.0",     # 产品版本
        "--file-description=从binglo提取SQL语句",  # 文件描述
        "--copyright=Copyright 2025",  # 版权信息
        "--enable-plugin=pyside6",     # 启用PySide6插件
        "main.py"                      # 主脚本
    ]

    subprocess.run(cmd, check=True)

    # 复制可执行文件到根目录
    exe_path = os.path.join(output_dir, "main.dist", "main.exe")
    if os.path.exists(exe_path):
        new_exe_path = os.path.join(output_dir, "main.dist", "binlog2sql.exe")
        shutil.move(exe_path, new_exe_path)
        print(f"构建完成！可执行文件已重命名并复制到: {new_exe_path}")
    else:
        print(f"构建完成，但未找到可执行文件: {exe_path}")
        print(f"请检查 {output_dir} 目录")

if __name__ == "__main__":
    build_executable()
