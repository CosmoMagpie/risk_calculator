# 情况分类公式计算

输出列表：
**第一层：现金流与资源消耗绝对值**

* 首日净现金流 = 客户端流入总额 - 交易端流出总额。
* 新增风险资本准备合计。
* 新增未来30日现金净流出。

**第二层：核心风控指标边际变动**

* 流动性覆盖率 (LCR) 变动
* 净稳定资金率 (NSFR) 变动
* 资本杠杆率变动

**第三梯队：动态性价比指标**

* 流动性创收率（RO-LCR） = 预期创收 / ｜首日净现金流出｜
* RO-NSFR（净稳定资金率性价比） = 预期创收 / $\Delta \text{所需稳定资金(RSF)}$
* 资本收益率（ROC） = 预期创收 / 新增风险资本准备。

## 场外期权产品

### 一、计算投资规模
名义本金：$N$（元）
权利金/收取金额：$P$（元）
$\pm 20\%$ 压力测试最大损失金额：$L_{\text{stress}}$（元）
公司分类评价调整系数：$k_{\text{class}}$（这里需要询问公司评级）
基于此，买入场外期权投资规模 $S_{\text{long}} = P$
卖出期权投资规模
$$S_{\text{short}} = \max\left(5 \times L_{\text{stress}},\, N \times 0.5\%\right)$$

### 二、计算市场风险资本准备
- 情况1：单边卖出
$$\text{RiskCap}_{\text{short}} = S_{\text{short}} \times 30\% \times k_{\text{class}}$$
- 情况2：单边买入
$$\text{RiskCap}_{\text{long}} = S_{\text{long}} \times 100\% \times k_{\text{class}} = P \times 100\% \times k_{\text{class}}$$
- 情况3：背靠背对冲
  首先判断是否达成有效对冲： 对冲比例 $R_{\text{delta}} = \left\vert{} \frac{\text{Delta}_{\text{hedge}}}{\text{Delta}_{\text{client}}} \right\vert{} \in [80\%, 125\%]$，且标的相关性 $\ge 95\%$。计算公式：
$$\text{RiskCap}_{\text{hedged}} = (\vert{}S_{\text{client}}\vert{} + \vert{}S_{\text{hedge}}\vert{}) \times 5\% \times k_{\text{class}}$$
注：$S_{\text{hedge}}$ 为对冲工具的投资规模。若为场外背靠背同上文算法；若为一揽子股票/现货，则为现货市值；若为场内股指期货，则为名义价值的15%。

### 三、指标边际变动

**1. 流动性覆盖率 (LCR) 变动量**
$$\Delta \text{LCR} = \frac{\text{HQLA}_{\text{base}} + \Delta \text{HQLA}}{\text{Outflow}_{\text{base}} + \Delta \text{Outflow}} - \text{LCR}_{\text{base}}$$
其中增量计算如下：
- a. 优质流动性资产增量（$\Delta \text{HQLA}$）需综合客户端与交易端（$\Delta \text{HQLA}_{\text{swap}} = \Delta \text{HQLA}_{\text{client}} + \Delta \text{HQLA}_{\text{hedge}}$）
   - 客户端：收到权利金 $\Delta \text{HQLA}_{\text{client}}= +P$ ；支付权利金 $\Delta \text{HQLA}_{\text{client}} = -P$
   - 交易端：若买入一揽子股票/ETF（沪深300/中证500/宽基）：现金流出导致 $\Delta \text{HQLA}_{\text{hedge}}$ 减少 100%市值，但买入的现货本身具有 50% 的 HQLA 折算率，故综合 $\Delta \text{HQLA}_{\text{hedge}} = - \text{现货市值} \times 50\%$。
    若买入一般股票或支付期货保证金、对冲期权权利金，相关资产折算率为 0%，因此综合 $\Delta \text{HQLA}_{\text{hedge}} = - 100\% \times \text{实际支付金额}$。
- b. 未来 30 日现金净流出增量（$\Delta \text{Outflow}$）对于卖出期权（场景 1），需计入 LCR 表外项目的资金流出折算：
$$\Delta \text{Outflow}_{\text{short}} = S_{\text{short}} \times 20\%$$

**2. 净稳定资金率 (NSFR) 变动量**
$$\Delta \text{NSFR} = \frac{\text{ASF}_{\text{base}} + \Delta \text{ASF}}{\text{RSF}_{\text{base}} + \Delta \text{RSF}} - \text{NSFR}_{\text{base}}$$
其中增量计算如下：
- a. 可用稳定资金增量（$\Delta \text{ASF}$）卖出期权收到的权利金 $P$ 增加公司现金，根据剩余存续期 $T$ 划分：若 $T < 6\text{个月}$：$\Delta \text{ASF} = P \times 0\% = 0$。若 $6\text{个月} \le T < 1\text{年}$：根据公司分类评价计入 0%~20%。若 $T \ge 1\text{年}$：$\Delta \text{ASF} = P \times 100\%$。
- b. 所需稳定资金增量（$\Delta \text{RSF}$）：
$$\Delta \text{RSF} = \Delta \text{RSF}_{\text{client}} + \Delta \text{RSF}_{\text{hedge}}$$
客户端增量：买入期权 $\Delta \text{RSF} = 0$ ；卖出期权 $\Delta \text{RSF} = S_{\text{short}} \times 12\%$。
交易端增量：包括现货对冲与表外衍生品对冲。
现货方面，沪深300 / 中证500 / 上证180 / 深证100 成份股：$\text{市值} \times 30\%$
宽基指数 ETF 现货：$\text{市值} \times 10\%$
一般上市股票：$\text{市值} \times 50\%$  流动受限股票 / 其他股票：$\text{市值} \times 100\%$
衍生品方面，场内股指期货：$\text{期货名义价值} \times 12\%$
场内/场外卖出期权：$\text{场内 Delta金额} \times 15\% \times 12\%$ 或 $\text{场外名义规模} \times 12\%$（$\text{Delta 金额} = \text{Delta 系数} \times \text{标的资产当前价格} \times \text{期权合约数量}$）
收益互换（多头/空头）：$\text{互换名义本金} \times 1\%$
以上加总为$\Delta \text{RSF}_{\text{hedge}}$

**3. 资本杠杆率变动**
$$\Delta \text{资本杠杆率} = \frac{\text{核心净资本}_{\text{base}}}{\text{表内外资产总额}_{\text{base}} + \Delta \text{表内外资产总额}} - \text{资本杠杆率}_{\text{base}}$$
其中$$\Delta \text{表内外资产总额} = \Delta \text{表内资产余额} + \Delta \text{表外项目余额}$$
$$\Delta \text{表外项目余额}=\Delta \text{表外}_{\text{client}} + \Delta \text{表外}_{\text{hedge}}$$
其中，$\Delta \text{表内资产余额}$等于首日净现金流入额。下面两个产品类似。
- a. 对于$\Delta \text{表外}_{\text{client}}$，买入期权时为0，卖出期权时
$$\Delta \text{表外}_{\text{client}} = S_{\text{short}} = \max\left(5 \times L_{\text{stress}},\, N \times 0.5\%\right)$$
- b. 对于$\Delta \text{表外}_{\text{hedge}}$
场内股指期货对冲：$\Delta \text{表外}_{\text{hedge}} = \text{期货名义价值} \times 15\%$
场内卖出期权对冲：$\Delta \text{表外}_{\text{hedge}} = \text{Delta金额} \times 15\%$
场外背靠背卖出期权平盘：$\Delta \text{表外}_{\text{hedge}} = \max\left(5 \times L_{\text{stress\_hedge}},\, N_{\text{hedge}} \times 0.5\%\right)$
现货 / ETF 对冲：$\Delta \text{表外}_{\text{hedge}} = 0$

### 四、动态变化指标变动
$$\text{ROC（资本收益率）} = \frac{\text{净预期创收}}{\text{RiskCap}}$$
$$\text{RO-LCR（流动性创收率）} = \frac{\text{净预期创收}}{\max\left(0,\, \Delta \text{Outflow} - \Delta \text{HQLA}\right)}$$
$$\text{RO-NSFR（稳定资金创收率）} = \frac{\text{净预期创收}}{\Delta \text{RSF}}$$

## 收益互换产品

### 一、计算投资规模与前置判断

* **输入变量：**
* 名义本金：$N$（元）
* 收取客户保证金/预付金金额：$M$（元）
* 公司分类评价调整系数：$k_{\text{class}}$

* **计算投资规模：**
$$S_{\text{swap}} = N \times 10\%$$

* **前置惩罚条件判断：**
* 条件A（非全额保证金）：$M < N$
* 条件B（个股标的）：标的为境内个股（非宽基/非指数）

### 二、计算风险资本准备

收益互换的资本占用分为市场风险与信用风险两部分。合计新增风险资本准备：
$$\text{RiskCap}_{\text{unhedged}} = \text{RiskCap}_{\text{market}} + \text{RiskCap}_{\text{credit}}$$

* **情况1：单边未对冲**
* a. 市场风险资本准备：
    $$\text{RiskCap}_{\text{market}} = S_{\text{swap}} \times 30\% \times k_{\text{class}} = N \times 3\% \times k_{\text{class}}$$
    *惩罚项：* 若同时满足条件A（非全额保证金）与条件B（境内个股），该笔市场风险资本准备需**加倍（即 $\times 2$）**。
* b. 信用风险资本准备（仅当满足条件A即非全额保证金时计提）：
    $$\text{RiskCap}_{\text{credit}} = N \times 5\% \times k_{\text{class}}$$

* **情况2：达成有效对冲**
判定条件同场外期权
* a. 市场风险资本准备：
    $$\text{RiskCap}_{\text{market\_hedged}} = (\vert{}S_{\text{swap}}\vert{} + \vert{}S_{\text{hedge}}\vert{}) \times 5\% \times k_{\text{class}}$$
    *惩罚项：* 同上，若同时满足条件A与条件B，对冲状态下的市场风险资本准备依然需**加倍（即 $\times 2$）**。
* b. 信用风险资本准备：
对冲不减免信用风险，若为非全额保证金，仍需计提 $\text{RiskCap}_{\text{credit}} = N \times 5\% \times k_{\text{class}}$。

### 三、指标边际变动

**1. 流动性覆盖率 (LCR) 变动量**

* a. 优质流动性资产增量（$\Delta \text{HQLA}$）：
    客户端$\Delta \text{HQLA}_{\text{client}} = + M$
    交易端流出及现货折算逻辑同场外期权模型
* b. 未来 30 日现金净流出增量（$\Delta \text{Outflow}$）：
收益互换作为自营业务及长期投资资金流出，需按名义本金折算计入增量：
$$\Delta \text{Outflow}_{\text{client}} = N \times 0.2\%$$

**2. 净稳定资金率 (NSFR) 变动量**

* a. 可用稳定资金增量（$\Delta \text{ASF}$）：
依据财务对所收保证金 $M$ 的期限与科目定性处理（若无确定期限或归入交易性负债，通常折算为0%）。
* b. 所需稳定资金增量（$\Delta \text{RSF}$）：
$$\Delta \text{RSF} = \Delta \text{RSF}_{\text{client}} + \Delta \text{RSF}_{\text{hedge}}$$
客户端增量：$\Delta \text{RSF}_{\text{client}} = N \times 1\%$
交易端增量（$\Delta \text{RSF}_{\text{hedge}}$）：与期权相同

**3. 资本杠杆率变动**
- a. 一般情况$\Delta \text{表外}_{\text{client}} = N \times 10\%$，惩罚情况翻倍。
- b. 对于$\Delta \text{表外}_{\text{hedge}}$，场外背靠背收益互换平盘时，按名义本金的 $10\%$（或惩罚项 $20\%$）计入。
场内股指期货对冲时，$\Delta \text{表外}_{\text{hedge}} = \text{期货名义价值} \times 15\%$。
现货 / ETF 对冲时，$\Delta \text{表外}_{\text{hedge}} = 0$。

### 四、动态变化指标变动
与场外期权业务相同

## 收益凭证业务

### 一、计算投资规模与前置判断
* **输入变量：**
* 募集资金总额：$V$（万元）
* 合约期限：$T$
* 公司分类评价调整系数：$k_{\text{class}}$
* **结构类型判定：** 是否为浮动收益凭证（含内嵌衍生品）？
* *若为"是"，需进一步输入内嵌期权参数：* 名义本金 $N$（万元）、$\pm 20\%$ 压力测试最大损失金额 $L_{\text{stress}}$（万元）。
* **计算投资规模（仅针对浮动收益凭证的内嵌期权部分）：**
内嵌衍生品视同卖出场外期权处理：
$$S_{\text{short}} = \max\left(5 \times L_{\text{stress}},\, N \times 0.5\%\right)$$

### 二、计算风险资本准备
收益凭证的本金负债部分不计提市场或信用风险资本准备。风险资本准备仅由**内嵌衍生品**触发。
* 情况1：固定收益凭证（无内嵌衍生品）
$$\text{RiskCap} = 0$$

* 情况2：浮动收益凭证（单边未对冲内嵌期权）
$$\text{RiskCap} = S_{\text{short}} \times 30\% \times k_{\text{class}}$$

* 情况3：浮动收益凭证（内嵌期权达成有效对冲）
*判定条件同场外期权（Delta匹配且相关性达标）。*
$$\text{RiskCap}_{\text{hedged}} = (\vert{}S_{\text{short}}\vert{} + \vert{}S_{\text{hedge}}\vert{}) \times 5\% \times k_{\text{class}}$$

### 三、指标边际变动

**1. 流动性覆盖率 (LCR) 变动量**
* a. $\Delta \text{HQLA}$：
    $$\Delta \text{HQLA} = V - \text{对冲占用现金净流出} + \text{新增对冲资产的HQLA折算值}$$
    募集本金 $V$ 带来 100% 货币资金流入。若将资金用于模块B对冲，买入现货/缴纳保证金会导致现金 100% 流出，需补偿新增资产的折算值（如沪深300现货补回 50%）。若完全不对冲，则 $\Delta \text{HQLA} = V$。
* b. $\Delta \text{Outflow}$：
    $$\Delta \text{Outflow} = \Delta \text{Outflow}_{\text{debt}} + \Delta \text{Outflow}_{\text{short}}$$
    * 债务本金部分（$\Delta \text{Outflow}_{\text{debt}}$）：若 $T \le 30\text{天}$，$\Delta \text{Outflow}_{\text{debt}} = V \times 100\%$；若 $T > 30\text{天}$，该项为 0。
    * 内嵌期权部分（$\Delta \text{Outflow}_{\text{short}}$）：若为浮动凭证，衍生品表外项目带来流出增量 $\Delta \text{Outflow}_{\text{short}} = S_{\text{short}} \times 20\%$。

**2. 净稳定资金率 (NSFR) 变动量**
* a. 可用稳定资金增量（$\Delta \text{ASF}$）：
依据凭证发行期限 $T$ 提供稳定资金池：
  * 若 $T \ge 1\text{年}$：$\Delta \text{ASF} = V \times 100\%$。
  * 若 $6\text{个月} \le T < 1\text{年}$：依据评级折算，$\Delta \text{ASF} = V \times (20\% \text{ 或 } 10\% \text{ 或 } 0\%)$。
  * 若 $T < 6\text{个月}$：$\Delta \text{ASF} = 0$。
* b. 所需稳定资金增量（$\Delta \text{RSF}$）：
    $$\Delta \text{RSF} = \Delta \text{RSF}_{\text{embedded}} + \Delta \text{RSF}_{\text{hedge}}$$
    * 内嵌期权部分（$\Delta \text{RSF}_{\text{embedded}}$）：若为浮动凭证，作为表外卖出衍生品，$\Delta \text{RSF}_{\text{embedded}} = S_{\text{short}} \times 12\%$。（固定收益凭证此项为 0）。
    * 交易对冲端（$\Delta \text{RSF}_{\text{hedge}}$）：同上。

**3. 资本杠杆率变动**
注意这里的表内增量为$V$本身
表外增量：
- a. 对于$\Delta \text{表内}_{\text{client}}$，固定收益凭证不使得其变化。
浮动收益凭证（内嵌期权）则视同表外卖出期权处理，计算公式与场外期权相同：$$\Delta \text{表外}_{\text{client}} = S_{\text{short\_embedded}} = \max\left(5 \times L_{\text{stress}},\, N \times 0.5\%\right)$$
- b. 对于$\Delta \text{表外}_{\text{hedge}}$，与场外期权相同。
