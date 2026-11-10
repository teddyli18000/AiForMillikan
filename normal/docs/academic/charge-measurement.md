# 单滴电荷计算

## 1. 轨迹与速度

后端从实际框选帧开始追踪，保留检测成功点并在用户确认的 \(0\ \mathrm{V}\) 窗口内拟合：

\[
y_i=s\,t_i+c.
\]

像素斜率 \(s\) 通过纵向标尺换算为下落速度：

\[
v=s\,k_y,
\]

其中 \(k_y\) 是 \(\mathrm{m/pixel}\) 标定系数。

拟合必须满足最少点数、最小时长、最小位移、\(R^2\) 和 missing ratio 条件；否则记录为 diagnostic。

## 2. Cunningham 修正半径

代码使用闭式正根。定义：

\[
\ell_c=\frac{b}{p},
\]

则：

\[
r=
\frac{
\sqrt{\ell_c^2+\frac{18\eta v}{\rho g}}-\ell_c
}{2}.
\]

有效黏度为：

\[
\eta_{\mathrm{eff}}
=
\frac{\eta}{1+\frac{b}{pr}}.
\]

## 3. 平衡电荷

结合平衡电场 \(E=U/d\)，Normal 当前实现使用：

\[
q
=
\frac{6\pi\eta_{\mathrm{eff}}rvd}{U}.
\]

程序报告正的电荷绝对值 `q_C`。平衡电压必须为有限正值，且用户必须明确确认油滴在该电压下处于平衡；软件不声称自动验证平衡。

## 4. 可审计计算链

每条 Normal record 的 `calculation_trace` 保存：

- 像素斜率与斜率标准误；
- 像素到物理长度比例；
- \(v\) 与 \(\sigma_v\)；
- 拟合点数、时长和 \(R^2\)；
- 平衡电压；
- Cunningham length、半径和有效黏度；
- \(q(v)\) 灵敏度；
- \(q\) 与 \(\sigma_q\)。

Stage 5 只排版这些 backend 值，不在 React 中重复计算物理结果。

## 5. 有效性

正式 q 至少要求：

- 拟合通过；
- \(v>0\)；
- \(r>0\)；
- \(q>0\)；
- \(\sigma_q\) 有限且为正；
- 所有 crossing 已复核为 `same_drop`；
- 用户明确点击接受。

不满足条件的记录仍保留为诊断和返回调整证据，但不能进入 Normal 盲反演。
