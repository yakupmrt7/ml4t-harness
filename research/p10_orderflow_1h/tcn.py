"""p10 model B: a small causal TCN on the raw 1-minute flow sequence (PLAN.md, fixed architecture).

Input: the 240 minutes ending at the bar close x 12 channels, standardised with the fold's
training statistics. 4 residual blocks (2 causal dilated Conv1d, kernel 3, 48 channels,
dilations 1/4/16/64, ReLU, dropout 0.2) -> [last step, time mean] -> linear -> 1 logit.
Uniqueness-weighted BCE on the same binary target as LightGBM (label > 0; label-0 rows are not
trained on but are predicted). AdamW lr 1e-3 wd 1e-4, batch 512, <= 30 epochs, early stopping
(patience 3) on the last 10% of the fold's training labels, purged by t1. Seed 0.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import torch
from torch import nn

SEQ, CH, WIDTH, DILATIONS, KERNEL, DROPOUT = 240, 12, 48, (1, 4, 16, 64), 3, 0.2
LR, WD, BATCH, MAX_EPOCHS, PATIENCE, VAL_FRAC, SEED = 1e-3, 1e-4, 512, 30, 3, 0.10, 0


class CausalConv(nn.Module):
    def __init__(self, cin, cout, d):
        super().__init__()
        self.pad = (KERNEL - 1) * d
        self.conv = nn.Conv1d(cin, cout, KERNEL, dilation=d)

    def forward(self, x):
        return self.conv(nn.functional.pad(x, (self.pad, 0)))


class Block(nn.Module):
    def __init__(self, cin, d):
        super().__init__()
        self.c1, self.c2 = CausalConv(cin, WIDTH, d), CausalConv(WIDTH, WIDTH, d)
        self.drop = nn.Dropout(DROPOUT)
        self.skip = nn.Conv1d(cin, WIDTH, 1) if cin != WIDTH else nn.Identity()

    def forward(self, x):
        h = self.drop(torch.relu(self.c1(x)))
        h = self.drop(torch.relu(self.c2(h)))
        return torch.relu(h + self.skip(x))


class TCN(nn.Module):
    def __init__(self):
        super().__init__()
        self.blocks = nn.Sequential(*[Block(CH if i == 0 else WIDTH, d) for i, d in enumerate(DILATIONS)])
        self.head = nn.Linear(2 * WIDTH, 1)

    def forward(self, x):                        # x: (B, CH, SEQ)
        h = self.blocks(x)
        return self.head(torch.cat([h[:, :, -1], h.mean(-1)], 1)).squeeze(1)


def device():
    return torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")


class Windows:
    """Sequences cut on the fly from one (T, CH) minute array kept ON THE DEVICE (no per-batch host copy);
    end[i] = row of the bar-close minute."""

    def __init__(self, M: np.ndarray, end: np.ndarray):
        self.M, self.end = M, end
        self.dev = device()
        self.Md = torch.from_numpy(np.nan_to_num(M).astype(np.float32)).to(self.dev)
        self.off = torch.arange(-SEQ + 1, 1, device=self.dev)

    def batch(self, idx, mean, std):
        e = torch.from_numpy(self.end[idx].astype(np.int64)).to(self.dev)
        x = self.Md[e[:, None] + self.off[None, :]]                        # (B, SEQ, CH)
        x = (x - torch.as_tensor(mean, device=self.dev)) / torch.as_tensor(std, device=self.dev)
        return x.transpose(1, 2).contiguous()


def valid_end_rows(minute_index: pd.DatetimeIndex, M: np.ndarray, t0: pd.DatetimeIndex) -> np.ndarray:
    """Row of each label's bar-close minute, or -1 if the 240-minute window is incomplete / has NaN."""
    rows = minute_index.get_indexer(t0)
    ok = rows >= SEQ - 1
    bad = np.isnan(M).any(1).astype(np.int64)
    cbad = np.concatenate([[0], np.cumsum(bad)])
    r = np.where(ok, rows, SEQ - 1)
    nan_in = cbad[r + 1] - cbad[r + 1 - SEQ] > 0
    return np.where(ok & ~nan_in & (rows >= 0), rows, -1)


def fit_predict(W: Windows, y, w, t0v, t1v, train, test, log=None):
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    dev = device()
    train = np.sort(train)
    n_val = max(1, int(len(train) * VAL_FRAC))
    val = train[-n_val:]
    fit = train[:-n_val]
    fit = fit[t1v[fit] < t0v[val[0]]]                                    # purge: labels ending inside val
    rows = W.end[fit]
    mean = W.M[rows].mean(0).astype(np.float32)
    std = (W.M[rows].std(0) + 1e-8).astype(np.float32)
    fit = fit[y[fit] >= 0]
    val = val[y[val] >= 0]
    wf = w[fit] / w[fit].mean()
    model = TCN().to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    lossf = nn.BCEWithLogitsLoss(reduction="none")
    best, best_state, bad = np.inf, None, 0
    rng = np.random.default_rng(SEED)
    for ep in range(MAX_EPOCHS):
        t = time.time()
        model.train()
        perm = rng.permutation(len(fit))
        for i in range(0, len(perm), BATCH):
            b = fit[perm[i:i + BATCH]]
            xb = W.batch(b, mean, std).to(dev)
            yb = torch.from_numpy(y[b].astype(np.float32)).to(dev)
            wb = torch.from_numpy(wf[perm[i:i + BATCH]].astype(np.float32)).to(dev)
            loss = (lossf(model(xb), yb) * wb).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        vl = weighted_loss(model, W, val, y, w, mean, std, dev)
        if log:
            log(f"    epoch {ep + 1} val_loss {vl:.5f} ({time.time() - t:.0f}s)")
        if vl < best - 1e-5:
            best, bad = vl, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= PATIENCE:
                break
    model.load_state_dict(best_state)
    return predict(model, W, test, mean, std, dev), {"epochs": ep + 1, "best_val_loss": float(best),
                                                      "n_fit": int(len(fit)), "n_val": int(len(val))}


@torch.no_grad()
def predict(model, W, idx, mean, std, dev):
    model.eval()
    out = []
    for i in range(0, len(idx), 4096):
        out.append(torch.sigmoid(model(W.batch(idx[i:i + 4096], mean, std).to(dev))).cpu().numpy())
    return np.concatenate(out) if out else np.array([])


@torch.no_grad()
def weighted_loss(model, W, idx, y, w, mean, std, dev):
    p = np.clip(predict(model, W, idx, mean, std, dev), 1e-6, 1 - 1e-6)
    yy, ww = y[idx], w[idx]
    return float(-(ww * (yy * np.log(p) + (1 - yy) * np.log(1 - p))).sum() / ww.sum())


def tcn_oos_predict(W: Windows, labels: pd.DataFrame, weights: pd.Series, splitter, log=print):
    """Same contract as harness.pipeline.oos_predict: P(up) on each test fold. Returns (preds, fold_info)."""
    y = np.where(labels["label"].to_numpy() > 0, 1, np.where(labels["label"].to_numpy() < 0, 0, -1))
    w = weights.reindex(labels.index).fillna(0).to_numpy()
    t0v = labels.index.to_numpy()
    t1v = labels["t1"].to_numpy()
    preds = pd.Series(np.nan, index=labels.index)
    info = []
    for k, (train, test) in enumerate(splitter.split(labels["t1"])):
        t = time.time()
        log(f"  TCN fold {k + 1}: train {len(train):,} test {len(test):,}")
        p, fi = fit_predict(W, y, w, t0v, t1v, train, test, log=log)
        preds.iloc[test] = p
        fi["fold"], fi["seconds"] = k + 1, round(time.time() - t)
        info.append(fi)
    return preds.dropna(), info
