from __future__ import annotations

import datetime
from numbers import Number
from typing import TYPE_CHECKING, List, Union, cast

import numpy as np
import pandas as pd

if TYPE_CHECKING:
   from .strategy import Strategy
   from .trade import Trade

def compute_drawdown_duration_peaks(dd: pd.Series):
    iloc = np.unique(np.r_[(dd == 0).values.nonzero()[0], len(dd) - 1])
    iloc = pd.Series(iloc, index=dd.index[iloc])
    df = iloc.to_frame('iloc').assign(prev=iloc.shift())
    df = df[df['iloc'] > df['prev'] + 1].astype(np.int64)

    # 取引がないためドローダウンがない場合、pandasの都合上以下を避けてnanシリーズを返す
    if not len(df):
        return (dd.replace(0, np.nan),) * 2

    df['duration'] = df['iloc'].map(dd.index.__getitem__) - df['prev'].map(dd.index.__getitem__)
    df['peak_dd'] = df.apply(lambda row: dd.iloc[row['prev']:row['iloc'] + 1].max(), axis=1)
    df = df.reindex(dd.index)
    return df['duration'], df['peak_dd']

def geometric_mean(returns: pd.Series) -> float:
    returns = returns.fillna(0) + 1
    if np.any(returns <= 0):
        return 0
    return np.exp(np.log(returns).sum() / (len(returns) or np.nan)) - 1

def _data_period(index) -> Union[pd.Timedelta, Number]:
    """データインデックスの期間をpd.Timedeltaとして返す"""
    values = pd.Series(index[-100:])
    return values.diff().dropna().median()

def compute_stats(
        trades: Union[List['Trade'], pd.DataFrame],
        equity: np.ndarray,
        index: pd.DatetimeIndex,
        strategy_instance: Strategy | None,
        risk_free_rate: float = 0,
) -> pd.Series:
    assert -1 < risk_free_rate < 1

   
    # エクイティカーブとインデックスの長さを一致させる
    if len(equity) > len(index):
        equity = equity[:len(index)]
    elif len(equity) < len(index):
        # エクイティカーブが短い場合は、0で埋める
        equity = np.concatenate([equity, np.full(len(index) - len(equity), 0)])
    
    dd = 1 - equity / np.maximum.accumulate(equity)
    dd_dur, dd_peaks = compute_drawdown_duration_peaks(pd.Series(dd, index=index))

    equity_df = pd.DataFrame({
        'Equity': equity,
        'DrawdownPct': dd,
        'DrawdownDuration': dd_dur},
        index=index)

    if isinstance(trades, pd.DataFrame):
        trades_df: pd.DataFrame = trades
        commissions = None  # Not shown
    else:
        # Backtest.run()から直接来たデータ
        trades_df = pd.DataFrame({
            'Code': [t.code for t in trades],
            'Size': [t.size for t in trades],
            'EntryBar': [t.entry_bar for t in trades],
            'ExitBar': [t.exit_bar for t in trades],
            'EntryPrice': [t.entry_price for t in trades],
            'ExitPrice': [t.exit_price for t in trades],
            'SL': [t.sl for t in trades],
            'TP': [t.tp for t in trades],
            'PnL': [t.pl for t in trades],
            'Commission': [t._commissions for t in trades],
            'ReturnPct': [t.pl_pct for t in trades],
            'EntryTime': [t.entry_time for t in trades],
            'ExitTime': [t.exit_time for t in trades],
        })
        trades_df['Duration'] = trades_df['ExitTime'] - trades_df['EntryTime']
        trades_df['Tag'] = [t.tag for t in trades]

        commissions = sum(t._commissions for t in trades)
    del trades

    pl = trades_df['PnL']
    returns = trades_df['ReturnPct']
    durations = trades_df['Duration']

    def _round_timedelta(value, _period=_data_period(index)):
        if not isinstance(value, pd.Timedelta):
            return value
        resolution = getattr(_period, 'resolution_string', None) or _period.resolution
        return value.ceil(resolution)

    s = pd.Series(dtype=object)
    s.loc['Start'] = index[0]
    s.loc['End'] = index[-1]
    s.loc['Duration'] = s.End - s.Start

    have_position = np.repeat(0, len(index))
    for t in trades_df.itertuples(index=False):
        have_position[t.EntryBar:t.ExitBar + 1] = 1

    s.loc['Exposure Time [%]'] = have_position.mean() * 100  # "n bars"時間単位、インデックス時間ではない
    s.loc['Equity Final [$]'] = equity[-1]
    s.loc['Equity Peak [$]'] = equity.max()
    if commissions:
        s.loc['Commissions [$]'] = commissions
    s.loc['Return [%]'] = (equity[-1] - equity[0]) / equity[0] * 100

    gmean_day_return: float = 0
    day_returns = np.array(np.nan)
    annual_trading_days = np.nan
    is_datetime_index = isinstance(index, pd.DatetimeIndex)
    if is_datetime_index:
        freq_days = cast(pd.Timedelta, _data_period(index)).days
        have_weekends = index.dayofweek.to_series().between(5, 6).mean() > 2 / 7 * .6
        annual_trading_days = (
            52 if freq_days == 7 else
            12 if freq_days == 31 else
            1 if freq_days == 365 else
            (365 if have_weekends else 252))
        freq = {7: 'W', 31: 'ME', 365: 'YE'}.get(freq_days, 'D')
        day_returns = equity_df['Equity'].resample(freq).last().dropna().pct_change()
        gmean_day_return = geometric_mean(day_returns)

    # 年率化リターンとリスク指標は、リターンが複利計算されるという（ほぼ正確な）
    # 仮定に基づいて計算される。参照: https://dx.doi.org/10.2139/ssrn.3054517
    # 我々の年率化リターンは`empyrical.annual_return(day_returns)`と一致するが、
    # リスクは一致しない。彼らは以下のより単純なアプローチを使用している。
    annualized_return = (1 + gmean_day_return)**annual_trading_days - 1
    s.loc['Return (Ann.) [%]'] = annualized_return * 100
    s.loc['Volatility (Ann.) [%]'] = np.sqrt((day_returns.var(ddof=int(bool(day_returns.shape))) + (1 + gmean_day_return)**2)**annual_trading_days - (1 + gmean_day_return)**(2 * annual_trading_days)) * 100  # noqa: E501
    # s.loc['Return (Ann.) [%]'] = gmean_day_return * annual_trading_days * 100
    # s.loc['Risk (Ann.) [%]'] = day_returns.std(ddof=1) * np.sqrt(annual_trading_days) * 100
    if is_datetime_index:
        time_in_years = (s.loc['Duration'].days + s.loc['Duration'].seconds / 86400) / annual_trading_days
        s.loc['CAGR [%]'] = ((s.loc['Equity Final [$]'] / equity[0])**(1 / time_in_years) - 1) * 100 if time_in_years else np.nan  # noqa: E501

    # 我々のSharpeは`empyrical.sharpe_ratio()`と一致しない。彼らは算術平均リターン
    # と単純な標準偏差を使用するため
    s.loc['Sharpe Ratio'] = (s.loc['Return (Ann.) [%]'] - risk_free_rate * 100) / (s.loc['Volatility (Ann.) [%]'] or np.nan)  # noqa: E501
    # 我々のSortinoは`empyrical.sortino_ratio()`と一致しない。彼らは算術平均リターンを使用するため
    with np.errstate(divide='ignore'):
        s.loc['Sortino Ratio'] = (annualized_return - risk_free_rate) / (np.sqrt(np.mean(day_returns.clip(-np.inf, 0)**2)) * np.sqrt(annual_trading_days))  # noqa: E501
    max_dd = -np.nan_to_num(dd.max())
    s.loc['Calmar Ratio'] = annualized_return / (-max_dd or np.nan)
    s.loc['Max. Drawdown [%]'] = max_dd * 100
    s.loc['Avg. Drawdown [%]'] = -dd_peaks.mean() * 100
    s.loc['Max. Drawdown Duration'] = _round_timedelta(dd_dur.max())
    s.loc['Avg. Drawdown Duration'] = _round_timedelta(dd_dur.mean())
    s.loc['# Trades'] = n_trades = len(trades_df)
    win_rate = np.nan if not n_trades else (pl > 0).mean()
    s.loc['Win Rate [%]'] = win_rate * 100
    s.loc['Best Trade [%]'] = returns.max() * 100
    s.loc['Worst Trade [%]'] = returns.min() * 100
    mean_return = geometric_mean(returns)
    s.loc['Avg. Trade [%]'] = mean_return * 100
    s.loc['Max. Trade Duration'] = _round_timedelta(durations.max())
    s.loc['Avg. Trade Duration'] = _round_timedelta(durations.mean())
    s.loc['Profit Factor'] = returns[returns > 0].sum() / (abs(returns[returns < 0].sum()) or np.nan) 
    s.loc['Expectancy [%]'] = returns.mean() * 100
    s.loc['SQN'] = np.sqrt(n_trades) * pl.mean() / (pl.std() or np.nan)
    s.loc['Kelly Criterion'] = win_rate - (1 - win_rate) / (pl[pl > 0].mean() / -pl[pl < 0].mean())

    s.loc['_strategy'] = strategy_instance
    s.loc['_equity_curve'] = equity_df
    s.loc['_trades'] = trades_df

    return s
