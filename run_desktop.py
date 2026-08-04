# ============================================================
# run_desktop.py - 桌面启动器（PyInstaller 打包入口）
# ============================================================
# 用法：
#   开发环境：python run_desktop.py
#   打包后：  直接双击生成的 .exe 文件
#
# 工作原理：
#   通过 Streamlit 内部 bootstrap API 启动 Web 服务，
#   自动打开浏览器，用户操作完成后关闭窗口即可退出。
# ============================================================

import os
import sys
import socket
import webbrowser
import threading
import time


def find_free_port(start: int = 8501, max_attempts: int = 100) -> int:
    """找到一个未被占用的端口"""
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 8501  # 兜底


def get_app_path() -> str:
    """获取 app.py 的路径（兼容 PyInstaller 打包与开发环境）"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后，sys._MEIPASS 是临时解压目录
        base_dir = sys._MEIPASS
    else:
        # 开发环境：run_desktop.py 所在目录
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # 优先查找项目根目录下的 app.py
    candidates = [
        os.path.join(base_dir, "app.py"),
        os.path.join(base_dir, "..", "app.py"),
        os.path.join(os.path.dirname(__file__), "app.py"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return os.path.abspath(p)

    raise FileNotFoundError(
        "未找到 app.py。请确保 app.py 与 run_desktop.py 在同一目录下。\n"
        f"已尝试路径：{candidates}"
    )


def setup_ifind_sdk():
    """让打包后的 iFinDPy 能找到 ctypes DLL。

    iFinDPy 在模块 import 时会在 sys.path 中寻找"以 site-packages 结尾"的条目，
    并加载 <条目>/iFinDAPI/Windows/bin/x64/ShellExport.dll。
    PyInstaller 冻结环境下 sys.path 没有这种结构，这里把打包进来的
    iFinDAPI/Windows 复制到 <_MEIPASS>/site-packages/iFinDAPI/Windows，
    并把 <_MEIPASS>/site-packages 追加到 sys.path（以 site-packages 结尾，满足其查找条件）。
    """
    if not getattr(sys, "frozen", False):
        return
    import shutil

    base = sys._MEIPASS  # PyInstaller onedir 模式 = dist/风控测算系统/_internal
    api_src = os.path.join(base, "iFinDAPI", "Windows")
    sp_dir = os.path.join(base, "site-packages")
    if os.path.isdir(api_src):
        sp_api = os.path.join(sp_dir, "iFinDAPI", "Windows")
        os.makedirs(os.path.dirname(sp_api), exist_ok=True)
        if not os.path.isdir(sp_api):
            print("[iFinD] 正在准备 iFinD 数据接口（首次启动稍慢）...")
            shutil.copytree(api_src, sp_api)
    if sp_dir not in sys.path:
        sys.path.append(sp_dir)


def main():
    """启动 Streamlit 应用"""
    # 必须在导入任何业务模块（含 iFinDPy）之前准备好 SDK 查找路径
    setup_ifind_sdk()

    app_path = get_app_path()
    port = find_free_port()

    # PyInstaller 的 onedir 布局会把 Streamlit 放到 _internal/streamlit，
    # 其源码路径不含 site-packages，Streamlit 因而可能误判为开发环境，
    # 不挂载前端静态资源并返回 404。环境变量须在导入 Streamlit 前设置；
    # 随后再通过配置 API 强制覆盖，兼容不同 Streamlit 版本。
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"

    # 设置环境变量（Streamlit 会读取）
    os.environ["STREAMLIT_SERVER_PORT"] = str(port)
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_THEME_BASE"] = "light"

    import streamlit.config as _st_config
    _st_config.set_option("global.developmentMode", False)

    print(f"[桌面启动器] 应用路径: {app_path}")
    print(f"[桌面启动器] 服务端口: {port}")
    print(f"[桌面启动器] 正在启动，请稍候...")

    # 延迟打开浏览器（等服务器启动）
    def open_browser():
        time.sleep(2)
        url = f"http://127.0.0.1:{port}"
        print(f"[桌面启动器] 正在打开浏览器: {url}")
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    # 通过 Streamlit 内部 API 启动
    # 注意：sys.argv 会影响 streamlit bootstrap 的行为
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
    ]

    try:
        import streamlit.web.bootstrap as bootstrap
        bootstrap.run(
            main_script_path=app_path,
            is_hello=False,
            args=[],
            flag_options={},
        )
    except KeyboardInterrupt:
        print("\n[桌面启动器] 用户中断，正在退出...")
    except SystemExit:
        pass
    except Exception as e:
        print(f"[桌面启动器] 运行异常: {e}")
        input("\n按回车键退出...")
        sys.exit(1)


if __name__ == "__main__":
    main()
