# 元电荷盲反演

## 输入

Normal 只使用满足以下条件的记录：

- `record.status == accepted`
- `record.kept == true`
- q 与 \(\sigma_q\) 有限且为正
- 所有 crossing 为 `same_drop`

至少需要 3 条记录。恰好 3 条时结果始终标记为 exploratory。

## 整数倍模型

假设：

\[
q_i \approx n_i e,
\qquad n_i\in\mathbb{Z}_{>0}.
\]

程序在固定搜索区间内扫描初值 \(e\)。对每个初值：

1. 分配 \(n_i=\operatorname{round}(q_i/e)\)；
2. 将 \(n_i\) 限制在允许整数范围；
3. 固定整数分配后进行带权重估计：

\[
\hat e
=
\frac{\sum_i n_iq_i/\sigma_{\mathrm{eff},i}^2}
{\sum_i n_i^2/\sigma_{\mathrm{eff},i}^2};
\]

4. 用新的 \(\hat e\) 重新分配 \(n_i\)；
5. 迭代到整数向量稳定或达到最大次数。

相同整数向量只保留残差较小的候选。

## 候选排序

归一化残差为：

\[
r_i=\frac{q_i-n_i\hat e}{\sigma_{\mathrm{eff},i}}.
\]

候选以：

\[
\chi^2=\sum_i r_i^2
\]

和 weighted RMS 排序。结果返回多个候选，而不是只给一个不可审查的数值。

## 输出诊断

结果包含：

- \(\hat e\) 与 \(\sigma_e\)；
- 每条记录的整数分配；
- 最近整数倍电荷；
- 绝对残差和归一化残差；
- 多个排序候选；
- 是否收敛；
- 是否命中搜索边界；
- 是否出现非本原整数分配；
- 小样本与残差 flags。

SI 精确定义值 \(1.602176634\times10^{-19}\ \mathrm{C}\) 只用于显示百分误差和相对不确定度，不参与搜索、排序或整数分配。

## 不能宣称的内容

Normal 1.0 没有拟合真实 continuous baseline，因此不会输出：

```text
quantized_favored
continuous_favored
```

当前图表展示的是整数倍对齐与残差诊断，不是量子化模型对连续模型的胜负证明。
