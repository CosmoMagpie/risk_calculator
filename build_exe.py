"""
build_exe.py - 将风控测算系统打包为 Windows 可执行文件夹

用法：
    python build_exe.py

输出：
    dist/风控测算系统/风控测算系统.exe  （双击运行）
"""

import subprocess
import sys
import os
import shutil


APP_NAME = "风控测算系统"
ENTRY_SCRIPT = "run_desktop.py"


def clean_dist():
    """清理旧的打包产物"""
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"[清理] 已删除 {d}/")
    # 清理 PyInstaller 生成的 .spec 文件
    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)


def build():
    """执行 PyInstaller 打包"""
    print("=" * 60)
    print(f"  正在打包: {APP_NAME}")
    print("=" * 60)

    # 确保在项目根目录执行
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    # 构建 PyInstaller 命令
    # --onedir: 生成文件夹（比 --onefile 更适合 Streamlit）
    # --collect-all streamlit: 收集 Streamlit 所有静态文件
    # --hidden-import: 确保某些隐式导入被包含
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--name", APP_NAME,
        "--console",                    # 显示控制台（方便查看日志）
        "--clean",
        "--noconfirm",
        # 收集 Streamlit 的全部文件（前端 JS/CSS/HTML）
        "--collect-all", "streamlit",
        # 确保子模块被包含
        "--hidden-import", "streamlit.web.bootstrap",
        "--hidden-import", "scipy.stats",
        "--hidden-import", "pandas",
        "--hidden-import", "numpy",
        # 添加项目文件
        "--add-data", f"backend{os.pathsep}backend",
        "--add-data", f"app.py{os.pathsep}.",
        # 入口脚本
        ENTRY_SCRIPT,
    ]

    print(f"\n[执行] {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print("\n[失败] 打包出错，请检查上方错误信息。")
        return False

    # 验证输出
    exe_path = os.path.join("dist", APP_NAME, f"{APP_NAME}.exe")
    if os.path.exists(exe_path):
        print(f"\n[成功] 打包完成！")
        print(f"  可执行文件: {os.path.abspath(exe_path)}")
        print(f"  输出目录:   {os.path.abspath(os.path.join('dist', APP_NAME))}")
        print(f"\n  将 'dist/{APP_NAME}' 文件夹复制到目标电脑，")
        print(f"  双击 '{APP_NAME}.exe' 即可运行。")
        return True
    else:
        print(f"\n[警告] 打包完成但未找到 {exe_path}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="打包风控测算系统")
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="仅清理旧的打包产物",
    )
    args = parser.parse_args()

    if args.clean_only:
        clean_dist()
        print("清理完成。")
    else:
        clean_dist()
        build()
