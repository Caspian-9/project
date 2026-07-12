import copy
from collections import defaultdict
from typing import Optional, Literal

import numpy as np
import pandas as pd
import polars as pl
import torch
import torch.nn as nn
import torch.optim as optim

from vnpy.alpha import (
    AlphaDataset,
    Segment,
    AlphaModel,
    logger
)


class LstmModel(AlphaModel):
    """
    LSTM神经网络模型

    使用LSTM神经网络实现的Alpha因子预测模型，主要功能包括:
    1. 构建和训练LSTM神经网络
    2. 预测Alpha因子值
    3. 模型评估和特征重要性分析
    4. 支持早停和防止过拟合
    """

    def __init__(
        self,
        input_size: int,                                # 输入特征维度
        hidden_size: int = 64,                          # LSTM隐藏层神经元数量
        num_layers: int = 2,                            # LSTM层数
        dropout: float = 0.0,                           # Dropout比率，用于防止过拟合
        n_epochs: int = 200,                            # 训练轮数
        lr: float = 0.001,                              # 学习率
        batch_size: int = 2000,                         # 每批训练样本数
        early_stop_rounds: int = 20,                    # 早停轮数
        optimizer: Literal["sgd", "adam"] = "adam",     # 优化器类型
        device: str = "cpu",                            # 训练设备
        seed: Optional[int] = None,                     # 随机数种子
    ) -> None:
        """
        初始化LSTM模型

        参数
        ----
        input_size : int
            输入特征的维度，即每个时间步的特征数量
        hidden_size : int
            LSTM隐藏层的神经元数量，决定了模型的容量
        num_layers : int
            LSTM的层数，层数越多模型越复杂
        dropout : float
            Dropout概率，用于减少过拟合，取值范围[0，1]
        n_epochs : int
            训练轮数，即遍历整个训练集的次数
        lr : float
            学习率，控制参数更新步长
        batch_size : int
            每次训练的样本数量
        early_stop_rounds : int
            早停轮数，当验证集性能不再提升时停止训练
        optimizer : str
            优化器类型，支持"adam"和"sgd"
        device : str
            训练设备，默认使用CPU
        seed : int, optional
            随机数种子，用于复现结果
        """
        # 保存模型超参数
        self.input_size: int = input_size
        self.hidden_size: int = hidden_size
        self.num_layers: int = num_layers
        self.dropout: float = dropout
        self.n_epochs: int = n_epochs
        self.lr: float = lr
        self.batch_size: int = batch_size
        self.early_stop_rounds: int = early_stop_rounds
        self.optimizer: str = optimizer
        self.device: str = device
        self.seed: Optional[int] = seed

        # 设置随机数种子以保证结果可复现
        if self.seed is not None:
            np.random.seed(self.seed)
            torch.manual_seed(self.seed)

        # 初始化LSTM网络结构
        self.model: LstmNetwork = LstmNetwork(
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
        )

        # 根据指定类型初始化优化器
        if optimizer.lower() == "adam":
            # Adam优化器，适用于大多数场景
            self.optimizer: optim.Optimizer = optim.Adam(
                self.model.parameters(),
                lr=self.lr
            )
        elif optimizer.lower() == "sgd":
            # 随机梯度下降优化器
            self.optimizer: optim.Optimizer = optim.SGD(
                self.model.parameters(),
                lr=self.lr
            )
        else:
            raise ValueError(f"不支持的优化器: {optimizer}")

        # 初始化模型状态
        self.fitted: bool = False      # 标记模型是否已训练
        self.device: str = device      # 训练设备

        # 添加特征名称列表
        self.feature_names: list[str] = []

    def fit(
        self,
        dataset: AlphaDataset,
        evals_result: dict | None = None,
    ) -> None:
        """
        训练LSTM模型

        使用给定的数据集训练LSTM模型，包含以下主要步骤:
        1. 准备训练集和验证集数据
        2. 迭代训练多个epoch
        3. 每个epoch后评估模型性能
        4. 实现早停机制防止过拟合
        5. 保存最佳模型参数

        参数
        ----
        dataset : AlphaDataset
            包含训练数据的数据集对象
        evaluation_results : dict
            用于存储训练过程中的评估指标
        """
        # 如果evals_result为None，初始化一个新的字典
        if evals_result is None:
            evals_result = {}

        # 存储训练和验证数据的字典
        train_valid_data: dict[str, dict] = defaultdict(dict)

        # 分别处理训练集和验证集
        for segment in [Segment.TRAIN, Segment.VALID]:
            # 获取学习数据并按时间和交易代码排序
            df: pl.DataFrame = dataset.fetch_learn(segment)
            df = df.sort(["datetime", "vt_symbol"])

            # 提取特征和标签
            features: np.ndarray = df.select(df.columns[2: -1]).to_numpy()
            labels: np.ndarray = np.array(df["label"])

            # 存储特征和标签数据
            train_valid_data["x"][segment] = features
            train_valid_data["y"][segment] = labels

            # 初始化评估结果列表
            evals_result[segment] = []

        # 早停相关变量初始化
        early_stop_count: int = 0           # 性能未提升的轮数
        best_valid_score: float = -np.inf   # 最佳验证集性能
        best_epoch: int = 0                 # 最佳epoch编号

        # 获取特征名称
        df = dataset.fetch_learn(Segment.TRAIN)
        self.feature_names = df.columns[2:-1]  # 跳过datetime和vt_symbol列，以及label列

        # 迭代训练epochs
        for epoch in range(self.n_epochs):
            logger.info(f"Epoch {epoch}:")

            # 训练阶段
            logger.info("training...")
            self._train_step(
                train_valid_data["x"][Segment.TRAIN],
                train_valid_data["y"][Segment.TRAIN]
            )

            # 评估阶段
            logger.info("evaluating...")
            train_loss, train_score = self._evaluate_step(
                train_valid_data["x"][Segment.TRAIN],
                train_valid_data["y"][Segment.TRAIN]
            )
            valid_loss, valid_score = self._evaluate_step(
                train_valid_data["x"][Segment.VALID],
                train_valid_data["y"][Segment.VALID]
            )

            # 打印当前训练和验证性能
            logger.info(f"train {train_score:.6f}, valid {valid_score:.6f}")

            # 记录评估结果
            evals_result[Segment.TRAIN].append(train_score)
            evals_result[Segment.VALID].append(valid_score)

            # 模型性能提升则更新最佳状态
            if valid_score > best_valid_score:
                best_valid_score = valid_score
                early_stop_count = 0
                best_epoch = epoch
                best_params = copy.deepcopy(self.model.state_dict())
            else:
                # 性能未提升则累加计数
                early_stop_count += 1
                # 达到早停条件则终止训练
                if early_stop_count >= self.early_stop_rounds:
                    logger.info("early stop")
                    break

        # 训练结束，输出最佳性能
        logger.info(f"best score: {best_valid_score:.6f} @ {best_epoch}")

        # 标记模型已训练
        self.fitted = True

        # 加载最佳模型参数
        self.model.load_state_dict(best_params)

    def _train_step(self, x_train: np.ndarray, y_train: np.ndarray) -> None:
        """
        训练一个完整的epoch

        使用小批量随机梯度下降法训练LSTM模型，主要步骤包括:
        1. 将数据转换为PyTorch张量并移至指定设备
        2. 前向传播计算预测值
        3. 计算损失函数
        4. 反向传播计算梯度
        5. 梯度裁剪防止梯度爆炸
        6. 更新模型参数

        参数
        ----
        x_train : np.ndarray
            训练数据的特征矩阵，形状为(样本数，特征数)
        y_train : np.ndarray
            训练数据的标签向量，形状为(样本数，)
        """
        # 将模型设置为训练模式，启用dropout等
        self.model.train()

        # 生成随机打乱的索引
        indices: np.ndarray = np.arange(len(x_train))
        np.random.shuffle(indices)

        # 按batch_size大小遍历数据
        for batch_start in range(0, len(indices), self.batch_size):
            if len(indices) - batch_start < self.batch_size:
                break

            # 准备当前batch的数据
            batch_indices: np.ndarray = indices[batch_start:batch_start + self.batch_size]
            batch_features: torch.Tensor = torch.from_numpy(x_train[batch_indices]).float().to(self.device)
            batch_labels: torch.Tensor = torch.from_numpy(y_train[batch_indices]).float().to(self.device)

            # 前向传播
            predictions: torch.Tensor = self.model(batch_features)
            loss: torch.Tensor = self._loss_fn(predictions, batch_labels)

            # 反向传播和参数更新
            self.optimizer.zero_grad()                                      # 清空之前的梯度
            loss.backward()                                                 # 计算梯度
            torch.nn.utils.clip_grad_value_(self.model.parameters(), 3.0)   # 梯度裁剪，防止梯度爆炸
            self.optimizer.step()                                           # 更新参数

    def _evaluate_step(self, x_data: np.ndarray, y_data: np.ndarray) -> tuple[float, float]:
        """
        评估一个完整的epoch

        在验证/测试阶段评估模型性能，主要步骤包括:
        1. 将模型设置为评估模式
        2. 按batch计算预测值
        3. 计算损失值和评估指标
        4. 返回整个数据集上的平均损失和评估分数

        参数
        ----
        x_data : np.ndarray
            测试数据的特征矩阵，形状为(样本数，特征数)
        y_data : np.ndarray
            测试数据的标签向量，形状为(样本数，)

        返回值
        ------
        tuple[float, float]
            返回(平均损失值，平均评估分数)
        """
        # 将模型设置为评估模式，关闭dropout等
        self.model.eval()

        # 存储每个batch的评估结果
        scores: list[float] = []
        losses: list[float] = []

        # 生成数据索引
        indices: np.ndarray = np.arange(len(x_data))

        # 按batch_size大小遍历数据
        for batch_start in range(0, len(indices), self.batch_size):
            if len(indices) - batch_start < self.batch_size:
                break

            # 准备当前batch的数据
            batch_indices: np.ndarray = indices[batch_start:batch_start + self.batch_size]
            batch_features: torch.Tensor = torch.from_numpy(x_data[batch_indices]).float().to(self.device)
            batch_labels: torch.Tensor = torch.from_numpy(y_data[batch_indices]).float().to(self.device)

            # 前向传播计算预测值
            with torch.no_grad():  # 关闭梯度计算
                predictions: torch.Tensor = self.model(batch_features)

            # 计算损失和评估指标
            batch_loss: torch.Tensor = self._loss_fn(predictions, batch_labels)
            batch_score: torch.Tensor = self._metric_fn(predictions, batch_labels)

            losses.append(batch_loss.item())
            scores.append(batch_score.item())

        # 返回整个数据集上的平均损失和评估分数
        return np.mean(losses), np.mean(scores)

    def _loss_fn(self, predictions: torch.Tensor, label: torch.Tensor) -> torch.Tensor:
        """
        计算模型预测值和真实标签之间的损失值

        在深度学习训练中，损失函数用于衡量模型预测结果与真实值之间的差异。
        目前仅支持均方误差(MSE)损失函数。

        参数
        ----
        predictions : torch.Tensor
            模型的预测输出张量
        label : torch.Tensor
            真实标签张量

        返回值
        ------
        torch.Tensor
            计算得到的MSE损失值张量
        """
        # 创建掩码标记出所有非NaN的标签值
        mask_valid: torch.Tensor = ~torch.isnan(label)

        # 计算预测值与真实值的差值的平方
        squared_error: torch.Tensor = (predictions[mask_valid] - label[mask_valid]) ** 2

        # 返回所有误差项的均值
        return torch.mean(squared_error)

    def _metric_fn(self, predictions: torch.Tensor, label: torch.Tensor) -> torch.Tensor:
        """
        计算模型评价指标

        使用负的损失函数值作为评价指标，分数越高代表模型效果越好。
        主要步骤包括:
        1. 过滤掉无效的标签值
        2. 计算预测值与真实值的损失
        3. 返回负的损失值作为评价分数

        参数
        ----
        predictions : torch.Tensor
            模型的预测值张量
        label : torch.Tensor
            真实标签张量

        返回值
        ------
        torch.Tensor
            评价指标得分，负的损失函数值
        """
        # 创建掩码标记出所有有限的标签值（排除inf和nan）
        mask: torch.Tensor = torch.isfinite(label)
        return -self._loss_fn(predictions[mask], label[mask])

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        使用训练好的LSTM模型进行预测

        对指定数据段进行预测，主要步骤包括:
        1. 检查模型是否已训练
        2. 准备推理数据
        3. 按批次进行预测
        4. 合并所有预测结果

        参数
        ----
        dataset : AlphaDataset
            包含待预测数据的数据集对象
        segment : Segment
            指定要预测的数据段

        返回值
        ------
        np.ndarray
            模型的预测结果数组

        异常
        ----
        ValueError
            当模型未经训练时抛出异常
        """
        # 检查模型是否已训练
        if not self.fitted:
            raise ValueError("模型尚未训练，请先训练模型！")

        # 获取推理数据并按时间和交易代码排序
        df = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])

        # 提取特征数据（去除前两列时间和代码，以及最后一列标签）
        feature_data: np.ndarray = df.select(df.columns[2: -1]).to_numpy()

        # 将模型设置为评估模式
        self.model.eval()
        predictions: list[np.ndarray] = []

        # 按批次大小进行预测
        total_samples: int = feature_data.shape[0]

        for start_idx in range(0, total_samples, self.batch_size):
            # 计算当前批次的结束索引
            if total_samples - start_idx < self.batch_size:
                end_idx: int = total_samples
            else:
                end_idx = start_idx + self.batch_size

            # 准备当前批次的输入数据
            batch_features: torch.Tensor = (
                torch.from_numpy(feature_data[start_idx:end_idx])
                .float()
                .to(self.device)
            )

            # 进行无梯度预测
            with torch.no_grad():
                batch_pred: np.ndarray = (
                    self.model(batch_features)
                    .detach()
                    .cpu()
                    .numpy()
                )
            predictions.append(batch_pred)

        # 合并所有批次的预测结果
        return np.concatenate(predictions)

    def detail(self) -> pd.DataFrame:
        """
        输出LSTM模型详细信息

        展示模型的关键信息，包括:
        1. 模型结构参数
        2. 训练状态信息
        3. 特征重要性分析

        返回值
        ------
        pd.DataFrame
            包含特征重要性分析结果的DataFrame
        """
        if not self.fitted:
            logger.info("模型尚未训练，无法显示详细信息")
            return None

        # 显示模型基本信息
        logger.info(f"输入特征维度: {self.input_size}")
        logger.info(f"LSTM隐藏层数量: {self.num_layers}")
        logger.info(f"每层神经元数量: {self.hidden_size}")

        # 计算模型总参数量
        total_params = sum(p.numel() for p in self.model.parameters())
        logger.info(f"模型总参数量: {total_params:,}")

        # 显示训练状态信息
        logger.info(f"训练设备: {self.device}")
        logger.info(f"当前学习率: {self.lr}")
        logger.info(f"批次大小: {self.batch_size}")

        # 计算特征重要性并以DataFrame形式展示
        importance_df: pd.DataFrame = self._calculate_feature_importance()
        return importance_df

    def _calculate_feature_importance(self) -> pd.DataFrame:
        """
        计算特征重要性

        通过扰动测试方法计算特征重要性，主要步骤包括:
        1. 生成测试样本
        2. 对每个特征添加噪声
        3. 计算预测变化程度
        4. 根据变化程度评估特征重要性

        返回值
        ------
        pd.DataFrame
            包含特征重要性分析结果的DataFrame，按重要性降序排列
        """
        self.model.eval()
        importance_dict: dict[str, float] = {}

        # 准备一批样本数据用于测试
        test_data: torch.Tensor = torch.randn(1000, self.input_size).to(self.device)
        base_pred: torch.Tensor = self.model(test_data).detach()

        # 对每个特征进行扰动测试
        noise_level: float = 0.1
        for i, feature_name in enumerate(self.feature_names):
            # 复制测试数据
            perturbed_data: torch.Tensor = test_data.clone()
            # 对特征i添加噪声
            perturbed_data[:, i] += torch.randn(1000).to(self.device) * noise_level
            # 计算预测变化
            with torch.no_grad():
                new_pred: torch.Tensor = self.model(perturbed_data)
                # 使用预测值变化的标准差作为重要性指标
                importance: float = torch.std(torch.abs(new_pred - base_pred)).item()
                importance_dict[feature_name] = importance

        # 创建DataFrame并按重要性降序排序
        df: pd.DataFrame = pd.DataFrame({
            'Feature': list(importance_dict.keys()),
            'Importance': list(importance_dict.values())
        })
        df = df.sort_values('Importance', ascending=False)
        df = df.set_index('Feature')

        # 返回特征重要性DataFrame
        return df


class LstmNetwork(nn.Module):
    """
    长短期记忆神经网络(LSTM)模型

    实现了LSTM神经网络的核心结构，主要功能包括:
    1. 构建多层LSTM网络
    2. 添加dropout防止过拟合
    3. 全连接层输出预测结果
    """

    def __init__(
        self,
        input_size: int = 6,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.0
    ) -> None:
        """
        构造LSTM网络

        参数
        ----
        input_size : int
            输入特征维度，即每个时间步的特征数量
        hidden_size : int
            LSTM隐藏层神经元数量，决定了模型的容量
        num_layers : int
            LSTM层数，层数越多模型越深
        dropout : float
            随机丢弃率，用于防止过拟合，取值范围[0，1]
        """
        super().__init__()

        # 定义LSTM层
        # - batch_first=True表示输入张量的形状为(batch_size，seq_len，input_size)
        # - dropout在多层LSTM之间添加Dropout层
        self.lstm: nn.LSTM = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
        )

        # 定义全连接输出层，将LSTM的输出映射到预测值
        self.fc: nn.Linear = nn.Linear(hidden_size, 1)

        # 保存输入特征维度，用于reshape操作
        self.input_size: int = input_size

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        前向传播函数

        定义了数据在网络中的流动路径，主要步骤包括:
        1. 重塑输入数据为LSTM期望的格式
        2. 通过LSTM层处理序列数据
        3. 取最后时间步的输出进行预测

        参数
        ----
        x : torch.Tensor
            输入数据张量，原始形状为(batch_size，features)

        返回值
        ------
        torch.Tensor
            模型预测输出，形状为(batch_size，)
        """
        # 重塑输入数据
        batch_size = len(x)
        x = x.reshape(batch_size, self.input_size, -1)  # [batch_size，input_size，seq_len]
        x = x.permute(0, 2, 1)                          # [batch_size，seq_len，input_size]

        # LSTM前向计算，_表示忽略状态输出(h_n，c_n)
        lstm_out, _ = self.lstm(x)                      # lstm_out: [batch_size，seq_len，hidden_size]

        # 取最后一个时间步的输出，通过全连接层得到预测值
        predictions = self.fc(lstm_out[:, -1, :])              # [batch_size，1]
        return predictions.squeeze()                           # [batch_size]
