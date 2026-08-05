# 股衍业务风险控制指标测算系统

本项目在《证券公司风险控制指标计算标准规定》的模型框架下，对场外期权、收益互换和收益凭证及其交易端头寸进行增量测算。系统输出现金与资源占用、核心风险控制指标边际变化，以及 ROC、RO-LCR、RO-NSFR 等性价比指标。


## 目录结构

```text
app.py                         Streamlit 前端
run_desktop.py                 Windows 桌面版启动器
build_exe.py                   PyInstaller 打包脚本
calculation.md                 模型依据、口径与公式
test_cases.md                  典型业务样例及最近一次输出
backend/
  analyzer.py                  统一计算编排入口
  config.py                    公司基数和监管参数
  models/                      客户端合约、交易端头寸数据模型
  calculators/                 风险资本、LCR、NSFR、杠杆率等计算模块
  services/ifind_client.py     iFinD 行情与 Greeks 接口
  test/                        回归测试和样例生成脚本
```

## 环境与启动

建议使用 64 位 Python。安装依赖：

```powershell
python -m pip install -r requirements.txt
```

iFinD Python 包由同花顺终端提供，不在公开依赖中。需要联机行情时，请确保 iFinD 终端及对应 Python 接口已正确安装。

开发方式启动：

```powershell
streamlit run app.py
```

桌面启动器：

```powershell
python run_desktop.py
```

## iFinD 凭据

应用前端可在本机运行时输入凭据。测试脚本也保留了空白凭据位置，但不得把真实账号和密码提交到 Git。

也可以仅在当前终端设置环境变量：

```powershell
$env:IFIND_USER_NAME = ""
$env:IFIND_PASSWORD = ""
```

## 测试

离线计算回归：

```powershell
python -m backend.test.test_calculators
python -m backend.test.test_integration
```

iFinD 联机接口检查：

```powershell
python -m backend.test.test_ifind_client
```

重新生成业务样例：

```powershell
python -m backend.test.generate_test_cases
```

`test_cases.md` 是一次运行快照，不是独立的计算依据。监管口径以 `calculation.md` 为准，代码实现以 `backend/` 为准。

## 打包与分发

```powershell
python build_exe.py
```

打包结果位于 `dist/风控测算系统/`。分发时必须复制整个目录，不能只复制其中的 EXE。

## 数据约定

- 除特别注明外，金额单位均为万元。
- 预期收益率和 Delta 使用小数，例如 `0.08` 表示 8%。
- 前端显示为百分数的保证金率、权利金率会在进入后端前转换成后端约定值。
- 公司基准参数集中在 `backend/config.py`；交付部署前必须替换为经财务、风险管理部门确认的实际数据。

