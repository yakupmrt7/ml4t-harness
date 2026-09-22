"""Glue: features + labels + splitter + model -> out-of-sample predictions."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def default_model():
    try:
        import lightgbm as lgb

        return lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.03,
            num_leaves=15,
            min_child_samples=200,   # large leaves: markets punish memorisation
            subsample=0.7,
            subsample_freq=1,
            colsample_bytree=0.7,
            reg_lambda=5.0,
            verbose=-1,
        )
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(max_leaf_nodes=15, min_samples_leaf=200, learning_rate=0.03)


def align(X: pd.DataFrame, labels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = X.dropna().index.intersection(labels.index)
    return X.loc[idx], labels.loc[idx]


def oos_predict(
    X: pd.DataFrame,
    labels: pd.DataFrame,
    splitter,
    model_factory: Callable = default_model,
    weights: pd.Series | None = None,
    y_override: np.ndarray | None = None,
) -> pd.Series:
    """Fit on each train fold, predict P(up) on the test fold.

    Rows with label 0 are excluded from training but still predicted.
    Returns a Series over the test positions only (NaN elsewhere dropped).
    y_override lets the null tests inject permuted labels.
    """
    X, labels = align(X, labels)
    y = (labels["label"].to_numpy() > 0).astype(int) if y_override is None else y_override
    nonzero = labels["label"].to_numpy() != 0
    w = None if weights is None else weights.reindex(labels.index).fillna(0).to_numpy()
    t1 = labels["t1"]
    preds = pd.Series(np.nan, index=labels.index)
    Xv = X.to_numpy()
    for train, test in splitter.split(t1):
        train = train[nonzero[train]]
        if len(train) < 100 or len(np.unique(y[train])) < 2:
            continue
        m = model_factory()
        kw = {} if w is None else {"sample_weight": w[train]}
        m.fit(Xv[train], y[train], **kw)
        preds.iloc[test] = m.predict_proba(Xv[test])[:, 1]
    return preds.dropna()


def oos_auc(preds: pd.Series, labels: pd.DataFrame) -> float:
    lab = labels.loc[preds.index, "label"]
    mask = lab != 0
    if mask.sum() < 10 or lab[mask].nunique() < 2:
        return np.nan
    return float(roc_auc_score(lab[mask] > 0, preds[mask]))
