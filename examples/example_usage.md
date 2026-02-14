# Trading Bot - Example Usage

## Basic Trading Scenarios

### Scenario 1: Simple Long Position

**Setup:**
- Symbol: AAPL
- Entry Price: $150.00
- Capital: $1,000
- Position Size: 6 shares (calculated: $30 / $150 = 0.2, rounded to minimum 3)

**Execution:**
```
1. Copy to clipboard: AAPL
2. Copy to clipboard: 150.00
3. Bot automatically:
   - Places buy order at $153.00 (2% above entry)
   - Waits for fill
   - Sets stop loss at $146.25 (2.5% below)
   - Monitors P&L
```

**Possible Outcomes:**

#### Outcome A: Quick Stop Out
```
Entry: $150.00
Stop Loss Hit: $146.50
Loss: -$21.00 (-3.5%)
Reentry Order: Placed at $150.00
```

#### Outcome B: Profitable Exit
```
Entry: $150.00
Price hits $199.50 (33% gain)
TP1 Hit: Sell 2 shares @ $199.50
Remaining: 4 shares
Continue holding...
```

### Scenario 2: Penny Stock Trade

**Setup:**
- Symbol: XYZ
- Entry Price: $0.75
- Position Size: 40 shares (calculated: $30 / $0.75)

**Execution:**
```
1. Copy to clipboard: XYZ
2. Copy to clipboard: 0.75
3. Bot automatically:
   - Places buy order at $0.77 (2% above)
   - Uses 4 decimal precision for price
   - Sets stop loss at $0.73
```

**Take Profit Levels:**
```
Entry: $0.75
TP1 (33%): $1.00 → Sell 13 shares
TP2 (66%): $1.25 → Sell 13 shares  
TP3 (99%): $1.49 → Sell 14 shares
```

### Scenario 3: Multiple Concurrent Positions

The bot can manage multiple positions simultaneously:

```
Terminal Output:

=== Capital: $5,000 ===
>>> Paste SYMBOL into clipboard...
    [AAPL copied]
>>> Now paste PRICE for AAPL into clipboard...
    [150.00 copied]
[AAPL] Initialized trader - Position size: 6
[AAPL] BUY order placed: 6 @ 153.00

=== Capital: $4,900 ===  
>>> Paste SYMBOL into clipboard...
    [TSLA copied]
>>> Now paste PRICE for TSLA into clipboard...
    [220.00 copied]
[TSLA] Initialized trader - Position size: 3
[TSLA] BUY order placed: 3 @ 224.40

[AAPL] FILLED: 6 @ 152.50
[AAPL] PnL monitoring active - $3.00 (0.33%)
[TSLA] FILLED: 3 @ 223.80
[TSLA] PnL monitoring active - $0.60 (0.09%)
```

## Advanced Usage

### Custom Position Sizing

Edit `Config` class:

```python
class Config:
    # Conservative sizing
    POSITION_CAPITAL = 20  # $20 per position
    MIN_POSITION_SIZE = 1
    
    # Aggressive sizing  
    POSITION_CAPITAL = 100  # $100 per position
    MIN_POSITION_SIZE = 5
```

### Adjusting Risk Parameters

```python
class Config:
    # Tighter stop loss
    STOP_LOSS_PCT = 0.985  # 1.5% stop
    
    # Wider stop loss
    STOP_LOSS_PCT = 0.96   # 4% stop
    
    # More reentry attempts
    MAX_REENTRIES = 10
    
    # Longer timeout
    TIMEOUT_MINUTES = 10
```

### Different Take Profit Strategy

```python
class Config:
    # Conservative (take profits earlier)
    TP_33_MULTIPLIER = 1.20  # 20% gain
    TP_66_MULTIPLIER = 1.40  # 40% gain
    TP_99_MULTIPLIER = 1.60  # 60% gain
    
    # Aggressive (hold for bigger gains)
    TP_33_MULTIPLIER = 1.50  # 50% gain
    TP_66_MULTIPLIER = 2.00  # 100% gain
    TP_99_MULTIPLIER = 3.00  # 200% gain
```

## Workflow Examples

### Morning Trading Routine

```bash
# 1. Start TWS/IB Gateway before market open
# 2. Launch trading bot
python trading_bot.py

# 3. Review pre-market movers in scanner (separate tool)
# 4. Select symbol from scanner
# 5. Copy symbol to clipboard
# 6. Check entry price on your charting software
# 7. Copy entry price to clipboard
# 8. Bot handles the rest

# 9. Repeat for additional positions
```

### Integration with Scanner

```bash
# Terminal 1: Run scanner
cd ../ibkr-scanner
python scanner.py

# Terminal 2: Run trading bot  
cd ../ibkr-trading-bot
python trading_bot.py

# Workflow:
# 1. Watch scanner for strong momentum
# 2. When ticker catches your eye, note the symbol
# 3. Check chart for entry point
# 4. Copy symbol and price to clipboard
# 5. Bot executes the trade
```

## State Transition Examples

### Example 1: Clean Profit Exit

```
[AAPL] STATE: IN_TRADE_PNL_U5
[AAPL] Managing position - PnL: 2.50%
[AAPL] STATE: IN_TRADE_PNL_O5
[AAPL] Above 5% profit - setting take profits
[AAPL] TP 33% set: 2 @ 199.50
[AAPL] TP 66% set: 2 @ 249.00
[AAPL] TP 99% set: 2 @ 298.50
[AAPL] STATE: IN_TRADE_PNL_O33
[AAPL] 33% take profit hit - 4 shares remaining
[AAPL] STATE: IN_TRADE_PNL_O66  
[AAPL] 66% take profit hit - 2 shares remaining
[AAPL] STATE: IN_TRADE_PNL_O99
[AAPL] 99% take profit hit - trade complete!
[AAPL] STATE: TRADE_COMPLETE
[AAPL] Trade complete - cleaning up
```

### Example 2: Stop Out with Reentry

```
[TSLA] STATE: IN_TRADE_PNL_U5
[TSLA] Managing position - PnL: -1.50%
[TSLA] Stop Loss filled: 3 @ 214.60
[TSLA] STATE: STOPPED_OUT
[TSLA] Stopped out - preparing reentry (attempt 1/5)
[TSLA] REENTRY order set: 3 @ 220.00
[TSLA] STATE: WAITING_REENTRY
[TSLA] Waiting for reentry... (attempt 1/5)
[TSLA] REENTRY #1 FILLED: 3 @ 220.50
[TSLA] STATE: IN_TRADE_PNL_U5
[TSLA] Managing position - PnL: 1.80%
[TSLA] STATE: IN_TRADE_PNL_O5
... continues ...
```

### Example 3: Profit Pullback

```
[NVDA] STATE: IN_TRADE_PNL_O33
[NVDA] 33% take profit hit - 4 shares remaining
[NVDA] PnL: 45% → 30% (pullback)
[NVDA] STATE: IN_TRADE_PNL_O5
[NVDA] PnL: 30% → 3% (continued pullback)  
[NVDA] STATE: IN_TRADE_PNL_U5
[NVDA] STOP LOSS set @ 195.00 (breakeven area)
```

## Emergency Procedures

### Clear Current Symbol

If you paste the wrong symbol:
```
Press: Ctrl+Shift+X
Result: Clipboard cleared, ready for new input
```

### Stop Bot Completely

```
Press: Ctrl+C
Result: Bot shuts down gracefully, closes IB connection
```

### Manual Position Override

If you need to manually close a position in TWS:
```
Bot will detect: Position manually closed
Bot action: Automatically transitions to TRADE_COMPLETE
Cleanup: All orders cancelled, tracking removed
```

## Tips for Success

### 1. Start Small
- Use paper trading account first
- Test with $10-20 position sizes
- Verify all features work as expected

### 2. Monitor Closely
- Watch first few trades carefully
- Verify order placements in TWS
- Check P&L calculations are accurate

### 3. Use with Scanner
- Let scanner identify momentum
- Use technical analysis for entry
- Bot handles execution and management

### 4. Risk Management
- Never risk more than 1-2% of capital per trade
- Set appropriate position sizes
- Don't overtrade - be selective

### 5. Keep Logs
- Review bot_logs/trading_bot.log daily
- Analyze winning vs losing trades
- Adjust parameters based on results
