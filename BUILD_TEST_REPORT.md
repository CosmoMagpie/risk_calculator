# 整合与测试报告

日期：2026-08-04

## 版本来源

- 模型与审计修订基线：GitHub `origin/yuhl`，提交 `13544f9`。
- EXE启动修复来源：GitHub `origin/yuhl2`，提交 `11e80a7`。
- `calculation.md`：恢复 `yuhl2` 中原有章节结构后，在原结构内订正现行监管公式。
- 典型样例：恢复原11例，补充新版业务字段和公司约束；账号、密码位置保留为空。

## EXE修复

PyInstaller onedir模式下，Streamlit位于 `_internal/streamlit`，路径不含 `site-packages`，可能误判 `global.developmentMode=True`，导致静态资源路由未挂载。`run_desktop.py` 现在于导入Streamlit前设置两种兼容环境变量，并通过配置API再次强制设置：

```text
STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false
STREAMLIT_GLOBAL_DEVELOPMENTMODE=false
global.developmentMode=False
```

## 验证结果

- 计算器回归：60/60通过。
- 集成与模型验证：132/132通过。
- iFinD脱敏脚本：凭据留空时2项通过、0项失败、1项跳过；不发起真实登录。
- 测试案例生成：成功生成TC01—TC11，共11例。
- Python语法编译：通过。
- PyInstaller 6.21.0、Python 3.14.0：构建成功。
- EXE进程启动后保持存活。
- `http://127.0.0.1:8501/`：HTTP 200，返回10,626字节。
- Streamlit打包静态资源：HTTP 200，不再出现主页/静态资源404。

## 产物

可执行文件位于：`dist/风控测算系统/风控测算系统.exe`。必须复制整个 `dist/风控测算系统` 文件夹，不能只复制EXE。

EXE SHA-256：`70093BF7CC7EB4854EB65AB8BD3BE836E7AAD5CE8A51D9206CB87BE6A81F3457`。

本次没有执行真实iFinD联机查询，因为测试凭据按要求留空；填写本机凭据后可单独运行 `python -m backend.test.test_ifind_client`。
