# Normal 不确定度

## 线性回归斜率不确定度

对：

\[
y_i=s\,t_i+c
\]

定义残差平方和：

\[
\mathrm{SSR}=\sum_i (y_i-\hat y_i)^2.
\]

当 \(N>2\) 时，残差方差估计为：

\[
\hat\sigma_y^2=\frac{\mathrm{SSR}}{N-2}.
\]

斜率标准误为：

\[
\sigma_s
=
\sqrt{
\frac{\hat\sigma_y^2}
{\sum_i(t_i-\bar t)^2}
}.
\]

速度不确定度：

\[
\sigma_v=|k_y|\sigma_s.
\]

这取代了早期由 RMSE、位移和 \(R^2\) 拼接的经验百分比，也没有在 q 层强加 5% floor。

## 非线性传播到 q

由 Cunningham 修正关系，当前实现使用速度到电荷的对数灵敏度：

\[
S_{q,v}
=
\frac{\partial\ln q}{\partial\ln v}
=
\frac{3(r+\ell_c)}{2r+\ell_c},
\qquad \ell_c=\frac{b}{p}.
\]

因此：

\[
\sigma_q
=
|q|S_{q,v}\frac{\sigma_v}{v}.
\]

如果 \(\sigma_v\) 或 \(\sigma_q\) 不可计算、非有限或非正，记录只能是 diagnostic。

## 当前 uncertainty budget

Normal 1.0 明确纳入：

- `velocity_fit_random`：0 V 线性回归斜率随机不确定度。

当前未纳入：

- 平衡电压不确定度；
- 标尺/measurement distance 不确定度；
- 极板距离不确定度；
- 黏度不确定度；
- 压力不确定度；
- 油密度不确定度；
- Cunningham 参数不确定度。

未定义的仪器误差不会被程序自行编造。UI 和导出报告必须显示 included 与 not included 列表。

## 反演中的数值 floor

Normal 反演可以使用：

\[
\sigma_{\mathrm{eff},i}^2
=
\sigma_{q_i}^2+\sigma_{\mathrm{floor}}^2
\]

防止数值权重爆炸。该 floor 属于反演权重，不会写回单滴 record，也不能冒充单滴实验不确定度。
