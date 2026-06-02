# 油滴轨迹筛选模型方案指引

## 1. 总目标

本训练子系统的目标不是预测油滴电荷量，也不是直接从视频中识别油滴。

它的目标是：

> 在前序视频算法已经提取出油滴轨迹之后，自动判断每条轨迹是否适合进入电荷量反演计算，并为每条轨迹输出可信度评分。

系统输入：

```text
视频算法输出的多油滴轨迹数据
```

系统输出：

```text
每条轨迹的 quality_score
是否保留
剔除原因
可解释特征
模型报告
```

最终服务于：

```text
高质量轨迹筛选
↓
单颗油滴 q 反演
↓
多油滴 q 分布统计
↓
元电荷 e 估计
```

---

## 2. 核心原则

### 2.1 不训练“电荷量预测模型”

禁止把模型设计成：

```text
video / trajectory → q
```

原因：

1. q 应由物理公式反演得到。
2. 直接预测 q 不可解释。
3. 数据量不足时容易过拟合。
4. 答辩时容易被质疑“为什么不用物理公式”。

正确目标是：

```text
trajectory features → quality_score
```

---

### 2.2 不依赖人工标注

本方案默认团队不做人工 good / bad 标注。

因此不采用传统监督分类路线：

```text
人工标签 good / bad
↓
训练分类器
```

而采用：

```text
硬规则过滤
+ 无监督异常检测
+ 物理一致性评分
+ 弱监督伪标签
```

---

### 2.3 ML 只做筛选，不替代物理

最终判断轨迹是否可信，要同时满足：

1. 轨迹本身稳定；
2. 速度拟合质量高；
3. 油滴形态稳定；
4. 多电压平台下物理反演结果一致；
5. 统计上不是明显异常点。

模型只是辅助排序和筛选，不应覆盖物理约束。

---

## 3. 推荐目录结构

建议在本地项目中新建：

```text
training_quality_filter/
```

目录结构如下：

```text
training_quality_filter/
├── README.md
├── configs/
│   └── default.yaml
├── data/
│   ├── input/
│   │   └── .gitkeep
│   ├── interim/
│   │   └── .gitkeep
│   ├── features/
│   │   └── .gitkeep
│   ├── models/
│   │   └── .gitkeep
│   └── reports/
│       └── .gitkeep
├── src/
│   └── qfilter/
│       ├── __init__.py
│       ├── schema.py
│       ├── features.py
│       ├── physics.py
│       ├── rules.py
│       ├── weak_labels.py
│       ├── unsupervised.py
│       ├── train.py
│       ├── score.py
│       ├── report.py
│       └── utils.py
├── scripts/
│   ├── extract_features.py
│   ├── train_unsupervised.py
│   ├── train_weak_model.py
│   ├── score_tracks.py
│   └── generate_report.py
├── tests/
│   ├── test_schema.py
│   ├── test_features.py
│   ├── test_rules.py
│   └── test_scoring.py
└── pyproject.toml
```

其中：

```text
data/input/
```

用于放前序视频算法导出的轨迹文件。

```text
data/features/
```

用于保存提取后的轨迹特征表。

```text
data/models/
```

用于保存训练好的筛选模型。

```text
data/reports/
```

用于保存筛选报告和实验结果。

---

## 4. 输入数据契约

前序视频算法应输出轨迹表，推荐格式为：

```text
tracks.parquet
```

或：

```text
tracks.csv
```

每一行代表某一帧中某一颗油滴的观测结果。

建议字段如下：

```text
video_id
track_id
frame_idx
time_s
x_px
y_px
radius_px
area_px
brightness
voltage_V
platform_id
is_valid_detection
```

字段含义：

| 字段 | 含义 |
|---|---|
| video_id | 视频编号 |
| track_id | 油滴轨迹编号 |
| frame_idx | 帧序号 |
| time_s | 当前时间，单位 s |
| x_px | 油滴中心横坐标，单位 px |
| y_px | 油滴中心纵坐标，单位 px |
| radius_px | 油滴半径估计，单位 px |
| area_px | 油滴面积，单位 px² |
| brightness | 油滴亮度或灰度均值 |
| voltage_V | 当前电压，单位 V |
| platform_id | 电压平台编号 |
| is_valid_detection | 当前帧检测是否可信 |

如果部分字段暂时没有，可以先保留为空，但以下字段必须存在：

```text
video_id
track_id
frame_idx
time_s
x_px
y_px
voltage_V
platform_id
```

---

## 5. 特征工程设计

每条轨迹最终被转换为一行特征。

### 5.1 轨迹完整性特征

```text
track_length
duration_s
missing_frame_ratio
valid_detection_ratio
num_platforms
num_voltage_changes
edge_proximity_min
```

意义：

- 轨迹太短，不适合计算；
- 断轨严重，容易产生错误速度；
- 离边界太近，容易丢失；
- 电压平台太少，无法做多平台一致性判断。

---

### 5.2 运动稳定性特征

对每个电压平台分别拟合：

```text
y(t) = v_y t + b
x(t) = v_x t + c
```

提取：

```text
vy_mean
vy_std_across_platforms
vx_abs_mean
speed_fit_r2_mean
speed_fit_r2_min
speed_fit_rmse_mean
speed_fit_rmse_max
acceleration_abs_mean
```

意义：

- 好轨迹在稳定电压平台内应近似匀速；
- y 方向速度用于 q 反演；
- x 方向漂移过大通常说明油滴受扰动或跟踪错误；
- 加速度项过大说明尚未达到稳态或存在碰撞 / 误跟踪。

---

### 5.3 形态稳定性特征

如果前序算法能输出油滴半径、面积、亮度，则提取：

```text
radius_cv
area_cv
brightness_cv
radius_jump_max
area_jump_max
brightness_jump_max
```

其中：

```text
cv = std / mean
```

意义：

- 同一颗油滴的大小和亮度不应剧烈变化；
- 突变可能意味着重叠、合并、分裂、焦距变化或轨迹串号。

---

### 5.4 物理一致性特征

在不同电压平台下，根据速度和物理公式反演 q，得到：

```text
q_i
```

然后提取：

```text
q_mean
q_std
q_cv
q_pairwise_relative_error
q_sign_consistency
physics_residual_mean
physics_residual_max
```

最重要的是：

```text
q_cv = std(q_i) / abs(mean(q_i))
```

如果同一颗油滴在多个电压平台下反演出的 q 差异很大，则该轨迹不可信。

---

### 5.5 统计异常特征

对所有轨迹整体统计后，可加入：

```text
distance_to_feature_median
robust_zscore_max
isolation_score
lof_score
```

意义：

- 一条轨迹即使单项指标不极端，也可能整体表现异常；
- 无监督异常检测可发现人工规则难覆盖的坏轨迹。

---

## 6. 筛选系统分层

推荐三层结构。

---

### 第一层：硬规则过滤

目的：快速排除明显不可用轨迹。

示例规则：

```text
track_length < min_track_length → reject
duration_s < min_duration_s → reject
num_platforms < 2 → reject
missing_frame_ratio > max_missing_ratio → reject
speed_fit_r2_min < min_r2 → reject
edge_proximity_min < min_edge_margin → reject
```

输出：

```text
hard_rule_pass
hard_rule_reasons
```

硬规则不应过度激进。  
它只负责排除明显错误，不负责精细排序。

---

### 第二层：无监督异常检测

推荐模型：

```text
Isolation Forest
Local Outlier Factor
Robust Z-score
```

第一版优先实现：

```text
Isolation Forest + RobustScaler
```

原因：

1. 不需要标注；
2. 对中小规模表格特征友好；
3. 工程实现简单；
4. 结果容易解释。

模型输入：

```text
trajectory feature table
```

模型输出：

```text
anomaly_score
```

注意：

```text
anomaly_score 越高表示越异常
```

实际进入综合评分时，应转换为：

```text
unsupervised_score = 1 - normalized_anomaly_score
```

---

### 第三层：物理一致性评分

根据速度拟合质量、q 一致性、形态稳定性构造物理质量分：

```text
physics_quality_score
```

建议初始公式：

```text
physics_quality_score =
    w1 * r2_score_component
  + w2 * q_consistency_component
  + w3 * morphology_stability_component
  + w4 * track_completeness_component
  + w5 * drift_penalty_component
```

所有 component 统一归一化到：

```text
0 ~ 1
```

最终综合分数：

```text
quality_score =
    α * hard_rule_score
  + β * physics_quality_score
  + γ * unsupervised_normality_score
```

建议初始权重：

```text
α = 0.30
β = 0.50
γ = 0.20
```

原因：

- 物理一致性最重要；
- 硬规则保证底线；
- 无监督模型作为辅助。

---

## 7. 弱监督增强方案

在无人工标注的前提下，可以用严格规则自动生成伪标签。

### 7.1 高置信 good

满足：

```text
track_length 足够长
num_platforms >= 2
missing_frame_ratio 很低
speed_fit_r2_min 很高
q_cv 很低
radius_cv / area_cv 较低
vx_abs_mean 较低
```

标记为：

```text
pseudo_label = good
```

---

### 7.2 高置信 bad

满足任意明显异常：

```text
track_length 极短
num_platforms < 2
missing_frame_ratio 很高
speed_fit_r2_min 很低
q_cv 很高
形态突变明显
横向漂移异常
```

标记为：

```text
pseudo_label = bad
```

---

### 7.3 中间样本

不参与训练：

```text
pseudo_label = uncertain
```

然后用 high-confidence good / bad 训练轻量模型：

```text
Random Forest
Gradient Boosting
Logistic Regression
```

第一版推荐：

```text
Random Forest
```

原因：

1. 小数据表现稳定；
2. 不要求复杂调参；
3. feature importance 可解释；
4. 适合答辩展示。

---

## 8. 推荐训练流程

### Step 1：读取轨迹

```text
tracks.parquet / tracks.csv
```

检查字段完整性、时间单调性、track_id 是否唯一。

---

### Step 2：提取特征

输出：

```text
data/features/track_features.parquet
```

每行一条轨迹。

---

### Step 3：硬规则筛选

输出：

```text
hard_rule_pass
hard_rule_reasons
```

---

### Step 4：训练无监督异常检测模型

输出：

```text
data/models/isolation_forest.joblib
data/models/scaler.joblib
```

---

### Step 5：生成伪标签

输出：

```text
pseudo_label
pseudo_label_confidence
```

---

### Step 6：训练弱监督模型

输出：

```text
data/models/weak_rf_model.joblib
```

如果伪标签样本太少，则跳过弱监督模型，只使用规则 + 无监督 + 物理评分。

---

### Step 7：综合评分

输出：

```text
data/reports/quality_scores.parquet
```

字段包括：

```text
video_id
track_id
quality_score
keep
reject_reasons
hard_rule_score
physics_quality_score
unsupervised_score
weak_model_score
```

---

### Step 8：生成报告

输出：

```text
data/reports/quality_report.html
data/reports/quality_report.json
```

报告应包括：

1. 总轨迹数量；
2. 保留轨迹数量；
3. 剔除轨迹数量；
4. 各类剔除原因统计；
5. quality_score 分布；
6. 关键特征分布；
7. q_cv 分布；
8. 保留前后 q 分布对比；
9. 估计元电荷 e 的稳定性对比。

---

## 9. 验收指标

不能只看模型 accuracy，因为没有人工标签。

应看这些指标：

### 9.1 轨迹层面

```text
保留率不应过低
剔除原因应可解释
低分轨迹应能在视频回放中观察到异常
```

建议：

```text
保留率初期控制在 20% ~ 70%
```

如果保留率低于 10%，通常说明规则太严。  
如果保留率高于 90%，通常说明筛选没起作用。

---

### 9.2 物理层面

筛选后应该满足：

```text
q_cv 平均值下降
速度拟合残差下降
q 分布更接近整数倍结构
元电荷 e 估计更稳定
```

---

### 9.3 实验报告层面

系统必须能解释：

```text
为什么保留这条轨迹？
为什么剔除这条轨迹？
哪些特征影响最大？
筛选前后 q 分布有什么变化？
```

如果不能解释，就不符合项目目标。

---

## 10. 第一版最小可行实现

第一版不要做复杂深度学习。

最小可行版本：

```text
schema.py
features.py
rules.py
unsupervised.py
score.py
report.py
```

实现功能：

1. 读取 tracks.csv / tracks.parquet；
2. 每条轨迹提取基础特征；
3. 使用硬规则剔除明显坏轨迹；
4. 使用 Isolation Forest 输出异常分；
5. 计算 physics_quality_score；
6. 输出 quality_scores.parquet；
7. 生成简单报告。

第一版先不做：

```text
CNN
YOLO
Transformer
端到端视频模型
复杂 GUI
大规模人工标注
```

---

## 11. 第二版增强方向

第二版再加入：

1. 弱监督伪标签；
2. Random Forest 质量模型；
3. 特征重要性分析；
4. q 分布整数倍拟合；
5. 元电荷 e 稳定性报告；
6. 可视化 top bad tracks / top good tracks；
7. 视频回放索引。

---

## 12. 最终对外表述

推荐写法：

> 本系统不采用端到端黑箱深度学习预测电荷量，而采用物理模型约束下的数据质量评估方法。系统首先由计算机视觉模块提取多油滴轨迹，再基于轨迹完整性、速度稳定性、形态稳定性和多电压平台下的电荷量反演一致性构造特征，通过无监督异常检测与弱监督伪标签学习，对每条轨迹进行自动可信度评分，从而筛选出适合参与 q 反演和元电荷统计估计的高质量油滴轨迹。

这个表述比“训练 AI 模型识别油滴电荷”更准确，也更容易答辩。
