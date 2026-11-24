Order slicing  -10 slices of 1.0 lot over 90 minutes. Same total position (10 lots), but each order is small enough to get filled near mid without spiking the price.

Basket / Multi-Symbol Execution — ⭐ Practical for Portfolios

POV = "match the market's pace." TWAP = "ignore the market, just keep a steady rhythm." POV is smarter with the data MT5 actually gives you.

Simple example
You want to buy 10 lots of EURUSD. Target POV = 10%.

Every 5 minutes, your EA checks: how many ticks happened in the last 5 minutes?

Time	Ticks in last 5 min	Your 10% share	You buy
09:00	400 ticks	40	0.4 lots
09:05	800 ticks	80	0.8 lots
09:10	200 ticks	20	0.2 lots
09:15	1000 ticks	100	1.0 lots
Result: You buy more when the market is active (easy to fill, low impact) and less when it's quiet (avoid moving price). Same total: 10 lots. But you blend into the market's natural rhythm.



Use walk-forward validation only

Net out transaction costs before declaring victory.






Notes: 2 Applicable Ideas
1. Directional Change (DC) Filter: Instead of watching price on a fixed time schedule, only react when price moves a meaningful threshold (e.g., 0.5%) from its last extreme. Small noise is ignored; a trade signal only fires when a real directional event is confirmed. This cuts whipsaw trades, reduces costs, and automatically filters choppy markets. Easy to code in MT5 with just one parameter (θ), and it replaces time bars with event-driven logic.

2. Modified Sharpe Selection: Don't pick a strategy by return alone — compare 2–3 EA variants using Return ÷ Max Drawdown (a risk-adjusted score) instead of standard Sharpe. Standard Sharpe can reward low-volatility strategies that barely make money, while this version forces you to confront worst-case pain. Run your variants in MT5 Strategy Tester, export equity curves, compute the ratio for each, and pick the one with the best score that still meets your minimum return target. Zero extra coding — just smarter comparison of backtests you already have.






quantify evverything
Quantifiable Traits from MT5 Data
Here's a complete map of everything MT5 gives you, converted into quantitative traits you can compute. I'll organize by data source.

A. Raw Data MT5 Provides
Data	What MT5 gives you
OHLC bars	Open, High, Low, Close per timeframe
Tick data	Every bid/ask change with timestamp
Bid/Ask	Live spread at any moment
Tick volume	Number of price changes per bar
Real volume	Only on exchange-traded symbols (stocks/futures), not FX/CFDs
Spread history	Ask − Bid over time
Time	Timestamps of every tick/bar
Account data	Balance, equity, margin, free margin
Order/deal history	Entry/exit price, volume, time, commission, swap, P&L
Symbol info	Contract size, tick size, tick value, min/max lot, swap rates
B. Quantifiable Traits — Derived from Price (OHLC)
1. Return-based
Trait	Formula
Simple return	(Close_t − Close_{t−1}) / Close_{t−1}
Log return	ln(Close_t / Close_{t−1})
Cumulative return	Close_t / Close_0 − 1
Mean return (per bar)	mean(returns)
Return skewness	skew(returns)
Return kurtosis	kurt(returns)
Autocorrelation of returns	corr(r_t, r_{t−k})
2. Volatility-based
Trait	Formula
Standard deviation of returns	std(returns)
Realized volatility	sqrt(sum(r²))
ATR (Average True Range)	mean(TR) over N bars
Parkinson volatility	sqrt(mean(ln(H/L)²) / (4ln2))
Garman-Klass volatility	Uses OHLC — more efficient than close-to-close
Rogers-Satchell volatility	Drift-independent OHLC estimator
Volatility of volatility	std(rolling_std(returns))
Volatility ratio	ATR(short) / ATR(long) — regime indicator
3. Range / Structure
Trait	Formula
Bar range	High − Low
Body size	|Close − Open|
Upper wick	High − max(Open, Close)
Lower wick	min(Open, Close) − Low
Body/range ratio	body / range — candle conviction
Gap	Open_t − Close_{t−1}
Range expansion	range_t / mean(range, N)
Consecutive up/down bars	Count
4. Trend / Direction
Trait	Formula
Moving average slope	(MA_t − MA_{t−k}) / k
Price vs MA distance	(Close − MA) / MA
MA crossover count	Number of sign changes in MA_fast − MA_slow
ADX (trend strength)	From +DI/−DI
Linear regression slope	slope(Close, N)
R² of trend	How well price fits a line
Higher highs / lower lows count	Structure detection
Efficiency ratio	|Close_t − Close_{t−N}| / sum(|Close_i − Close_{i−1}|) — trendiness vs choppiness
5. Mean-reversion / Oscillation
Trait	Formula
RSI	Standard 14-period
Bollinger Band position	(Close − MA) / (2×std)
Z-score of price	(Close − mean) / std
Distance from VWAP-like anchor	(Close − anchor) / anchor
Hurst exponent	Long-range dependence (0.5 = random, >0.5 = trending)
Autocorrelation of price changes	Mean-reversion signal
Half-life of mean reversion	From Ornstein-Uhlenbeck fit
C. Quantifiable Traits — Derived from Tick Data
Trait	Formula
Tick count per bar	MT5 tick volume
Tick rate	ticks / seconds — activity intensity
Average time between ticks	1 / tick_rate
Tick size distribution	Histogram of price changes per tick
Up-tick / down-tick ratio	count(Δprice>0) / count(Δprice<0) — order flow proxy
Tick direction autocorrelation	Persistence of micro-momentum
Realized spread	2 × |trade_price − mid| (from your fills)
Effective spread	Same, measured per fill
Quoted spread	Ask − Bid at any moment
Spread mean / std / skew	Distribution of spread over time
Spread by time-of-day	Hourly average spread
Spread volatility	std(spread)
Tick imbalance	(up_ticks − down_ticks) / total_ticks — order flow imbalance proxy
Volume-synchronized probability	Tick volume per unit time as activity measure
D. Quantifiable Traits — Derived from Spread
Trait	Formula
Current spread	Ask − Bid
Spread in pips/points	Normalize by tick size
Spread as % of price	(Ask − Bid) / Mid
Average spread (N bars)	mean(spread, N)
Spread z-score	(spread − mean) / std — "is spread unusually wide?"
Spread by hour	Group by hour of day
Spread spike frequency	Count of spread > threshold
Rollover spread inflation	Spread during rollover vs. normal
Spread-to-ATR ratio	spread / ATR — cost relative to opportunity
E. Quantifiable Traits — Derived from Volume (Tick Volume)
Trait	Formula
Tick volume per bar	Raw MT5 value
Volume moving average	mean(tick_vol, N)
Volume ratio	tick_vol / mean(tick_vol, N) — relative activity
Volume z-score	(tick_vol − mean) / std
Volume trend	slope(tick_vol, N)
Volume-price correlation	corr(tick_vol, |return|)
On-balance volume (OBV)	Cumulative signed volume
Volume-weighted price (proxy)	sum(price × tick_vol) / sum(tick_vol) — tick-VWAP proxy
Volume spike count	Bars where tick_vol > 2× mean
Volume clustering	Autocorrelation of volume
F. Quantifiable Traits — Derived from Time
Trait	Formula
Hour of day	0–23
Day of week	1–5
Session (Asia/London/NY)	Categorical → dummy
Time since session open	Minutes
Time to session close	Minutes
Time since last news (if known)	Minutes
Bar duration	Fixed per timeframe
Time between DC events	See directional change below
Intraday seasonality	Average return/vol by hour
G. Quantifiable Traits — Derived from Your Orders/Deals
Trait	Formula
Fill price vs. arrival mid	Slippage (signed)
Effective spread cost	2 × |fill − mid|
Time-to-fill	fill_time − order_time
Fill rate	filled / submitted
Partial fill ratio	filled_volume / requested_volume
Commission per lot	From deal history
Swap cost	From deal history
Adverse selection	mid_{t+5s} − mid_fill (signed)
Realized P&L per trade	From deal history
Holding time	exit_time − entry_time
MAE (Maximum Adverse Excursion)	Worst price against you during trade
MFE (Maximum Favorable Excursion)	Best price for you during trade
Trade frequency	Trades per day/week
Win rate	wins / total
Average win / average loss	Ratio
Profit factor	gross_profit / gross_loss
Expectancy	(win_rate × avg_win) − (loss_rate × avg_loss)
Consecutive wins/losses	Max streak
Turnover	Total volume traded per period
H. Quantifiable Traits — Derived from Account/Equity Curve
Trait	Formula
Equity curve slope	Linear regression on equity
Max drawdown	max(peak − trough) / peak
Average drawdown	Mean of all drawdowns
Drawdown duration	Time from peak to recovery
Ulcer index	sqrt(mean(drawdown²)) — pain measure
Calmar ratio	return / maxDD
Sharpe ratio	(mean_return − rf) / std_return
Sortino ratio	(mean_return − rf) / downside_std
Recovery factor	net_profit / maxDD
Exposure	time_in_market / total_time
Margin utilization	used_margin / equity
Risk of ruin	Function of win rate, payoff, bet size
I. Quantifiable Traits — Derived from Symbol Info
Trait	Source
Contract size	SymbolInfoDouble(SYMBOL_TRADE_CONTRACT_SIZE)
Tick size	SYMBOL_TRADE_TICK_SIZE
Tick value	SYMBOL_TRADE_TICK_VALUE
Min/max/step lot	SYMBOL_VOLUME_MIN/MAX/STEP
Swap long / short	SYMBOL_SWAP_LONG/SHORT
Swap mode	Points / money / interest
Margin requirement	SYMBOL_MARGIN_INITIAL
Stop level	SYMBOL_TRADE_STOPS_LEVEL
Freeze level	SYMBOL_TRADE_FREEZE_LEVEL
Digits	SYMBOL_DIGITS
Point	SYMBOL_POINT
Derived traits:

Cost per lot in account currency = spread × tick_value / tick_size

Spread as % of tick value

Minimum trade cost = min_lot × spread_cost

Swap-adjusted holding cost per day

J. Quantifiable Traits — Directional Change (DC) Framework
Trait	Formula
DC threshold θ	Chosen parameter (e.g., 0.5%)
Number of DC events	Count
Average DC event duration	mean(time between events)
DC event size	price move per event
DC event frequency	events / time
Up-event vs. down-event ratio	Directional bias
Time in DC vs. time in noise	% time inside threshold
DC-based volatility	std(event sizes)
DC trend persistence	Autocorrelation of event directions
K. Composite / Derived Traits (Combining Sources)
Trait	Formula
Volatility-adjusted spread	spread / ATR
Liquidity score	tick_volume / spread — activity per unit cost
Market efficiency	|return| / range — directional conviction
Trend quality	efficiency_ratio × ADX
Noise ratio	1 − efficiency_ratio
Risk-adjusted momentum	return / volatility
Cost-adjusted expectancy	expectancy − spread_cost − slippage
Regime indicator	Combine ATR ratio + ADX + Hurst
Signal-to-noise	mean_return / std_return per bar
Trade quality	MFE / MAE per trade
Execution quality	1 − (effective_cost / spread)