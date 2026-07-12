import numpy as np
import lightgbm as lgb
import pandas as pd
from typing import Optional

from vnpy.alpha.dataset import AlphaDataset, Segment
from vnpy.alpha.model import AlphaModel


class DoubleensembleModel(AlphaModel):
    """
    Double Ensemble 模型

    通过训练多个子模型(子集成), 并可选地进行样本重加权(Sample Reweighting)及特征选择(Feature Selection)
    来实现双重集成的预测模型。主要功能包括:
    1. 多个基础模型的集成训练
    2. 样本重加权策略, 根据损失表现调整样本的重要性
    3. 特征选择策略, 通过打乱特征评估其对于模型损失的影响
    4. 最终将所有子模型的预测结果加权平均, 形成最终的预测结果
    """

    def __init__(
        self,
        base_model: str = "gbm",                         # 基础模型类型，默认为 LightGBM
        loss: str = "mse",                               # 损失函数类型，默认为均方误差
        num_models: int = 3,                             # 子模型数量
        enable_sr: bool = True,                          # 是否启用样本重加权
        enable_fs: bool = True,                          # 是否启用特征选择
        alpha1: float = 1.0,                             # 样本重加权中 h1 的系数
        alpha2: float = 1.0,                             # 样本重加权中 h2 的系数
        bins_sr: int = 10,                               # 样本重加权的分箱数
        bins_fs: int = 5,                                # 特征选择的分箱数
        decay: float = 0.5,                              # 权重衰减系数
        sample_ratios: list[float] = [
            1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0
        ],                                               # 不同分箱对应的特征采样比例
        epochs: int = 28,                                # 训练轮数（num_boost_round）
        early_stopping_rounds: Optional[int] = None,     # 提前停止轮数
        **kwargs,
    ) -> None:
        """
        初始化 Double Ensemble 模型参数

        参数
        ----
        base_model : str
            基础模型类型, 默认为 LightGBM("gbm")
        loss : str
            损失函数类型, 当前支持 "mse"
        num_models : int
            子模型数量, 代表要训练的基础模型个数
        enable_sr : bool
            是否启用样本重加权(Sample Reweighting)机制
        enable_fs : bool
            是否启用特征选择(Feature Selection)机制
        alpha1 : float
            样本重加权中 h1 的系数
        alpha2 : float
            样本重加权中 h2 的系数
        bins_sr : int
            样本重加权分箱数
        bins_fs : int
            特征选择分箱数
        decay : float
            权重衰减系数, 用于在样本重加权时抑制过度放大的样本重要性
        sample_ratios : list of float
            分箱对应的特征采样比例, 在特征选择中使用
        epochs : int
            训练轮数(num_boost_round)
        early_stopping_rounds : int, optional
            提前停止轮数, 默认为 None 表示不进行提前停止
        **kwargs :
            其他传递给 LightGBM 的参数, 如正则化系数、线程数等
        """
        # 保存模型超参数
        self.base_model: str = base_model
        self.num_models: int = num_models
        self.enable_sr: bool = enable_sr
        self.enable_fs: bool = enable_fs
        self.alpha1: float = alpha1
        self.alpha2: float = alpha2
        self.bins_sr: int = bins_sr
        self.bins_fs: int = bins_fs
        self.decay: float = decay
        self.sample_ratios: list[float] = sample_ratios
        self.sub_weights: list[float] = [1] * self.num_models
        self.epochs: int = epochs
        self.early_stopping_rounds: Optional[int] = early_stopping_rounds
        self.valid_loss: float = float('inf')

        # 设置全局随机种子
        self.seed = kwargs.get("seed", None)
        if self.seed:
            self.rng = np.random.RandomState(self.seed)
        else:
            self.rng = np.random.RandomState()

        # 将 LightGBM 的参数添加到模型配置中
        self.params: dict = {
            "objective": loss,  # 损失函数
            "colsample_bytree": 0.8879,  # 特征采样率
            "learning_rate": 0.2,  # 学习率
            "subsample": 0.8789,  # 数据采样率
            "lambda_l1": 205.6999,  # L1 正则化
            "lambda_l2": 580.9768,  # L2 正则化
            "max_depth": 8,  # 树最大深度
            "num_leaves": 210,  # 叶子节点数
            "num_threads": 20,  # 线程数
            "verbosity": -1,  # 日志输出等级
            **kwargs,
        }

        # 初始化模型属性
        self.ensemble: list[lgb.Booster] = []  # 用于存储所有子模型
        self.sub_features: list[pd.Index] = []  # 用于存储每个子模型的特征
        self.loss: str = loss  # 损失函数名称

    def fit(self, dataset: AlphaDataset) -> None:
        """
        训练 Double Ensemble 模型

        主要步骤:
        1. 从给定数据集中提取训练集和验证集
        2. 循环训练 num_models 个子模型
        3. 在训练过程中, 根据配置选择是否执行样本重加权和特征选择
        4. 记录并更新子模型集合及其特征子集

        参数
        ----
        dataset : AlphaDataset
            数据集对象, 包含训练数据和验证数据
        """
        # 获取训练集和验证集并按时间和交易代码排序
        df_train = dataset.fetch_learn(Segment.TRAIN)
        df_train = df_train.sort(["datetime", "vt_symbol"])

        df_valid = dataset.fetch_learn(Segment.VALID)
        df_valid = df_valid.sort(["datetime", "vt_symbol"])

        # 将数据转换为 pandas DataFrame
        train_data: pd.DataFrame = df_train.to_pandas()
        valid_data: pd.DataFrame = df_valid.to_pandas()

        # 提取特征和标签
        x_train, y_train = train_data.iloc[:, 2:-1], train_data["label"].values  # 特征和标签

        # 初始化样本权重
        weights: pd.Series = pd.Series(np.ones(x_train.shape[0], dtype=float))

        # 提取特征列名
        features: pd.Index = x_train.columns

        # 初始化子模型预测结果
        pred_sub: pd.DataFrame = pd.DataFrame(
            np.zeros((x_train.shape[0], self.num_models), dtype=float),
            index=x_train.index
        )

        # 清空之前的模型和特征集合，确保重新训练时不会累加
        self.ensemble = []
        self.sub_features = []

        for k in range(self.num_models):
            # 记录当前子模型的特征集合
            self.sub_features.append(features)

            # 训练单个子模型并将其保存在 ensemble 中
            model_k: lgb.Booster = self.train_submodel(train_data, valid_data, weights, features)
            self.ensemble.append(model_k)

            # 如果已训练到第 num_models 个模型, 则跳出循环
            if k + 1 == self.num_models:
                break

            # 提取该子模型对训练集的增量损失曲线
            loss_curve: pd.DataFrame = self.retrieve_loss_curve(model_k, train_data, features)

            # 获取该子模型对训练集的预测
            pred_k: pd.Series = self.predict_sub(model_k, train_data, features)
            pred_sub.iloc[:, k] = pred_k

            # 计算当前集成(包括已训练好的 k+1 个子模型)对训练集的预测
            pred_ensemble = (
                (pred_sub.iloc[:, : k + 1] * self.sub_weights[: k + 1]).sum(axis=1)
                / np.sum(self.sub_weights[: k + 1])
            )
            # 计算当前集成模型的损失(此时共 k+1 个模型)
            loss_values: pd.Series = pd.Series(self.get_loss(y_train, pred_ensemble.values))

            # 若开启样本重加权, 则更新样本权重
            if self.enable_sr:
                weights = self.sample_reweight(loss_curve, loss_values, k + 1)

            # 若开启特征选择, 则更新特征集合
            if self.enable_fs:
                features = self.feature_selection(train_data, loss_values)

        # 获取最后一个子模型在验证集上的增量损失曲线, 计算验证集平均损失
        loss_curve_valid: pd.DataFrame = self.retrieve_loss_curve(self.ensemble[-1], valid_data, features)
        self.valid_loss = loss_curve_valid.iloc[:, -1].mean()

    def train_submodel(self, train_data: pd.DataFrame, valid_data: pd.DataFrame, weights: pd.Series, features: pd.Index) -> lgb.Booster:
        """
        训练单个子模型

        使用 LightGBM 进行单个子模型的训练, 并返回训练好的模型对象。
        主要步骤:
        1. 构造 LightGBM Dataset
        2. 设置必要的回调函数(如日志输出、记录评估信息、提前停止等)
        3. 调用 lgb.train 进行训练

        参数
        ----
        train_data : pd.DataFrame
            训练数据 DataFrame, 包含特征与标签
        valid_data : pd.DataFrame
            验证数据 DataFrame, 用于训练过程中的模型评估
        weights : pd.Series
            样本权重序列, 用于调控不同样本在损失中的贡献
        features : pd.Index
            当前使用的特征集合

        返回值
        ------
        model : lightgbm.Booster
            训练完成的 LightGBM 模型对象
        """
        # 准备训练与验证数据
        dataset_train, dataset_valid = self._prepare_data_gbm(train_data, valid_data, weights, features)
        # 设置回调函数
        evals_result: dict = dict()
        callbacks: list = [lgb.log_evaluation(20), lgb.record_evaluation(evals_result)]

        # 设置提前停止
        if self.early_stopping_rounds:
            callbacks.append(lgb.early_stopping(self.early_stopping_rounds))

        # 训练模型
        model: lgb.Booster = lgb.train(
            self.params,
            dataset_train,
            num_boost_round=self.epochs,
            valid_sets=[dataset_train, dataset_valid],
            valid_names=["train", "valid"],
            callbacks=callbacks,
        )

        # 返回训练好的模型
        return model

    def _prepare_data_gbm(self, train_data: pd.DataFrame, valid_data: pd.DataFrame, weights: pd.Series, features: pd.Index) -> tuple[lgb.Dataset, lgb.Dataset]:
        """
        准备训练与验证数据, 转换为 LightGBM Dataset 格式

        参数
        ----
        train_data : pd.DataFrame
            训练数据
        valid_data : pd.DataFrame
            验证数据
        weights : pd.Series
            样本权重
        features : pd.Index
            特征列表

        返回值
        ------
        tuple(lightgbm.Dataset, lightgbm.Dataset)
            分别为训练集与验证集对应的 LightGBM Dataset
        """
        # 提取训练集和验证集的特征和标签
        x_train, y_train = train_data[features], train_data["label"]
        x_valid, y_valid = valid_data[features], valid_data["label"]
        # 将标签转换为numpy数组
        y_train = np.array(y_train)
        y_valid = np.array(y_valid)

        # 创建训练集和验证集的 LightGBM Dataset
        dataset_train: lgb.Dataset = lgb.Dataset(x_train, label=y_train, weight=weights)
        dataset_valid: lgb.Dataset = lgb.Dataset(x_valid, label=y_valid)

        # 返回训练集和验证集的 LightGBM Dataset
        return dataset_train, dataset_valid

    def sample_reweight(self, loss_curve: pd.DataFrame, loss_values: pd.Series, k_th: int) -> pd.Series:
        """
        样本重加权(Sample Reweighting)模块

        通过比较模型在若干棵树(前后期)上的损失变化, 以及当前集成模型预测的损失,
        为每个样本分配新的权重, 使得困难样本或近期误差增大的样本得到更高权重。

        参数
        ----
        loss_curve : pd.DataFrame
            当前子模型对训练集增量预测的损失曲线, 行为样本, 列为每棵树的损失
        loss_values : pd.Series
            集成模型在当前阶段对训练样本的损失
        k_th : int
            当前子模型在集成中的索引(从 1 开始计数)

        返回值
        ------
        pd.Series
            更新后的样本权重序列
        """
        # 对损失曲线进行归一化处理，转换为百分比排名
        loss_curve_norm: pd.DataFrame = loss_curve.rank(axis=0, pct=True)
        # 对集成模型损失取负并归一化，使得损失越小排名越高
        loss_values_norm: pd.Series = (-loss_values).rank(pct=True)                   # 越大越好, 故取负号

        N, T = loss_curve.shape
        # 取损失曲线前10%的树作为起始阶段
        part: int = max(int(T * 0.1), 1)
        # 计算起始阶段和结束阶段的平均损失
        l_start: pd.Series = loss_curve_norm.iloc[:, :part].mean(axis=1)
        l_end: pd.Series = loss_curve_norm.iloc[:, -part:].mean(axis=1)

        # h1表示当前集成模型的整体损失表现
        h1: pd.Series = loss_values_norm
        # h2表示样本在训练过程中损失变化趋势，end/start比值越大表示样本越难学习
        h2: pd.Series = (l_end / l_start).rank(pct=True)
        # 结合h1和h2，按照alpha1和alpha2的权重计算综合评分
        h: pd.DataFrame = pd.DataFrame({"h_value": self.alpha1 * h1 + self.alpha2 * h2})

        # 将综合评分h_value进行分箱，每个箱子中的样本具有相同的权重
        h["bins"] = pd.cut(h["h_value"], self.bins_sr)
        # 计算每个箱子中样本的平均权重
        h_avg: pd.Series = h.groupby("bins")["h_value"].mean()
        # 初始化样本权重序列，所有样本初始权重为0
        weights: pd.Series = pd.Series(np.zeros(N, dtype=float))

        # 遍历每个箱子，计算每个箱子中样本的权重，评分越低权重越高
        for b in h_avg.index:
            # 使用指数衰减计算权重，随着k_th增加，权重衰减越快
            weights[h["bins"] == b] = 1.0 / (self.decay**k_th * h_avg[b] + 0.1)

        return weights

    def feature_selection(self, train_data: pd.DataFrame, loss_values: pd.Series) -> pd.Index:
        """
        特征选择(Feature Selection)模块

        通过对每个特征进行打乱, 观察集成模型在该干扰下的损失变化, 从而评估特征的重要性。
        然后根据重要性进行分箱并按照一定比例进行特征采样, 得到新的特征集合。

        参数
        ----
        train_data : pd.DataFrame
            训练数据
        loss_values : pd.Series
            当前集成模型在训练集上的损失序列

        返回值
        ------
        pd.Index
            更新后的特征集合, 包含选定的特征
        """
        # 提取训练集的特征和标签
        x_train, y_train = train_data.iloc[:, 2:-1], train_data["label"]
        # 提取特征列名
        features: pd.Index = x_train.columns
        # 获取特征数量
        N, F = x_train.shape

        # 初始化特征重要性评分
        g: pd.DataFrame = pd.DataFrame({"g_value": np.zeros(F, dtype=float)})
        # 获取子模型数量
        M: int = len(self.ensemble)

        # 复制训练集，用于打乱特征
        x_train_tmp: pd.DataFrame = x_train.copy()

        # 遍历每个特征
        for i_f, feat in enumerate(features):
            # 打乱单个特征的值，用于评估该特征的重要性
            x_train_tmp.loc[:, feat] = self.rng.permutation(x_train_tmp.loc[:, feat].values)
            pred: pd.Series = pd.Series(np.zeros(N), index=x_train_tmp.index)

            # 使用所有子模型对打乱特征后的数据进行预测
            for i_s, submodel in enumerate(self.ensemble):
                pred += (
                    pd.Series(
                        submodel.predict(x_train_tmp.loc[:, self.sub_features[i_s]].values),
                        index=x_train_tmp.index
                    ) / M
                )

            # 计算打乱特征后的损失
            loss_feat: np.ndarray = self.get_loss(y_train.values.squeeze(), pred.values)
            # 计算特征重要性评分，使用均值和标准差归一化，变化越大表示特征越重要
            g.loc[i_f, "g_value"] = np.mean(loss_feat - loss_values) / (
                np.std(loss_feat - loss_values) + 1e-7
            )

            # 恢复原特征
            x_train_tmp.loc[:, feat] = x_train.loc[:, feat].copy()

        # 将特征重要性评分替换为0，避免出现NaN
        g["g_value"].replace(np.nan, 0, inplace=True)
        # 将特征重要性评分进行分箱，每个箱子中的特征具有相同的权重
        g["bins"] = pd.cut(g["g_value"], self.bins_fs)

        # 初始化特征列表
        res_feat: list[str] = []
        # 将特征重要性评分进行排序，从高到低
        sorted_bins: list[pd.Interval] = sorted(g["bins"].unique(), reverse=True)
        # 遍历每个箱子
        for i_b, b in enumerate(sorted_bins):
            # 获取该箱子中的特征
            b_feat: pd.Index = features[g["bins"] == b]
            # 计算该箱子中特征的数量
            num_feat: int = int(np.ceil(self.sample_ratios[i_b] * len(b_feat)))
            # 从该箱子中随机选择特征
            res_feat = res_feat + self.rng.choice(b_feat, size=num_feat, replace=False).tolist()

        # 如果设置了随机种子, 则对特征列表进行排序
        if self.seed:
            result = pd.Index(sorted(set(res_feat)))
        else:
            result = pd.Index(set(res_feat))

        # 返回特征列表
        return result

    def get_loss(self, label: np.ndarray, pred: np.ndarray) -> np.ndarray:
        """
        计算损失函数

        当前仅支持均方误差(MSE):
        loss = (label - pred)^2

        参数
        ----
        label : np.ndarray
            真实标签
        pred : np.ndarray
            模型预测值

        返回值
        ------
        np.ndarray
            每个样本对应的损失值
        """
        # 如果损失函数为均方误差(MSE), 则计算损失
        if self.loss == "mse":
            return (label - pred) ** 2
        else:
            raise ValueError("not implemented yet")

    def retrieve_loss_curve(self, model: lgb.Booster, train_data: pd.DataFrame, features: pd.Index) -> pd.DataFrame:
        """
        提取损失曲线

        逐棵树对训练集进行增量预测, 记录各阶段的损失值。
        即, 第 i 棵树的预测是在前 i-1 棵树基础上累加得到的, 然后计算并保存损失。

        参数
        ----
        model : lightgbm.Booster
            训练完成的子模型
        train_data : pd.DataFrame
            训练数据
        features : pd.Index
            特征集合

        返回值
        ------
        pd.DataFrame
            每棵树对应的损失曲线, 行为样本, 列为树索引
        """
        # 获取模型中树的数量
        num_trees: int = model.num_trees()
        # 提取训练集的特征和标签
        x_train, y_train = train_data[features], train_data["label"]
        # 将标签转换为numpy数组
        y_train = np.array(y_train)

        N: int = x_train.shape[0]
        # 初始化损失曲线矩阵，每行是一个样本，每列是一棵树的累积预测损失
        loss_curve: pd.DataFrame = pd.DataFrame(np.zeros((N, num_trees)))
        # 初始化累积预测值
        pred_tree: np.ndarray = np.zeros(N, dtype=float)

        # 逐棵树累积预测并计算损失
        for i_tree in range(num_trees):
            # 累积预测
            pred_tree += model.predict(x_train, start_iteration=i_tree, num_iteration=1)
            # 计算损失
            loss_curve.iloc[:, i_tree] = self.get_loss(y_train, pred_tree)

        # 返回损失曲线
        return loss_curve

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        使用已训练好的集成模型进行预测

        对指定数据片段(Segment)进行推断, 并返回预测结果。

        参数
        ----
        dataset : AlphaDataset
            包含待预测数据的数据集
        segment : Segment
            指定要预测的数据片段(如训练集、验证集或测试集)

        返回值
        ------
        np.ndarray
            集成模型的预测结果

        异常
        ----
        ValueError
            当模型尚未训练时抛出异常
        """
        # 如果模型尚未训练, 则抛出异常
        if not self.ensemble:
            raise ValueError("model is not fitted yet!")

        # 获取待预测数据
        df_infer: pd.DataFrame = dataset.fetch_infer(segment)
        df_infer = df_infer.sort(["datetime", "vt_symbol"])

        # 将待预测数据转换为DataFrame
        x_test: pd.DataFrame = df_infer.to_pandas()

        # 初始化预测结果
        pred: pd.Series = pd.Series(np.zeros(x_test.shape[0]), index=x_test.index)

        # 遍历每个子模型
        for i_sub, submodel in enumerate(self.ensemble):
            # 获取该子模型所使用的特征
            feat_sub: pd.Index = self.sub_features[i_sub]
            # 累积预测
            pred += pd.Series(submodel.predict(x_test[feat_sub].values), index=x_test.index) \
                * self.sub_weights[i_sub]

        # 返回预测结果
        return pred / np.sum(self.sub_weights)

    def predict_sub(self, submodel: lgb.Booster, df_data: pd.DataFrame, features: pd.Index) -> pd.Series:
        """
        使用指定的子模型对给定数据进行预测

        参数
        ----
        submodel : lightgbm.Booster
            要进行预测的子模型
        df_data : pd.DataFrame
            待预测的数据 DataFrame
        features : pd.Index
            对应该子模型所使用的特征集合

        返回值
        ------
        pd.Series
            该子模型对数据的预测结果
        """
        # 提取数据中的特征
        x_data: pd.DataFrame = df_data[features]

        # 返回预测结果
        return pd.Series(submodel.predict(x_data), index=x_data.index)

    def get_feature_importance(self, *args, **kwargs) -> pd.Series:
        """
        获取特征重要性

        将各子模型的特征重要性(可同时获取split和gain两种类型),
        乘以相应子模型的权重后进行加和, 最终根据重要性得分进行降序排列。

        参数
        ----
        *args :
            传递给 submodel.feature_importance 的位置参数
        **kwargs :
            传递给 submodel.feature_importance 的关键字参数

        返回值
        ------
        pd.Series
            每个特征对应的加权综合重要性, 按降序排列
        """
        # 初始化结果列表
        res: list[pd.Series] = []
        # 遍历每个子模型
        for _model, _weight in zip(self.ensemble, self.sub_weights):
            # 获取该子模型的特征重要性
            res.append(
                pd.Series(_model.feature_importance(*args, **kwargs),
                          index=_model.feature_name()) * _weight
            )

        # 将结果列表连接起来
        return pd.concat(res, axis=1, sort=False).sum(axis=1).sort_values(ascending=False)

    def detail(self) -> None:
        """
        显示模型细节

        主要展示特征的重要性图表(split 和 gain两种类型),
        以帮助分析模型对不同特征的依赖程度和贡献。
        """
        # 遍历两种特征重要性类型
        for importance_type in ["split", "gain"]:
            # 绘制特征重要性图表
            ax = lgb.plot_importance(
                self.ensemble[0],
                max_num_features=50,
                importance_type=importance_type,
                figsize=(10, 20)
            )
            ax.set_title(f"Feature Importance ({importance_type})")
