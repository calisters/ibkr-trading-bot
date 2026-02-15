# IBKR Momentum Trading Bot - DEADHAND v2.0

A sophisticated algorithmic trading bot for Interactive Brokers that implements a clipboard-based tactical execution interface with multi-level take-profits, dynamic position sizing, and automated reentry logic.

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

## 🎯 Features

### Core Trading Capabilities
- **Clipboard-Based Execution**: Paste symbol and entry price for instant trade setup
- **Dynamic Position Sizing**: Automatically calculates optimal position size based on available capital
- **Multi-Level Take Profits**: Systematic profit-taking at 33%, 66%, and 99% gains
- **Intelligent Stop Loss**: 2.5% stop loss with automatic adjustment based on profit levels
- **Reentry System**: Automatically reenters positions after stop-outs (up to 5 attempts)
- **Real-Time P&L Monitoring**: Live tracking of unrealized profit/loss

### Risk Management
- **State Machine Architecture**: Robust state-based trade management
- **Position Integrity Checks**: Continuous verification of broker vs tracked positions
- **Emergency Hotkeys**: Quick clipboard clear for emergency stop
- **Comprehensive Logging**: Full audit trail of all trading actions

### Technical Features
- **Asynchronous Architecture**: Non-blocking concurrent trade management
- **Price Precision Handling**: Automatic adjustment for penny stocks vs regular stocks
- **Order Validation**: Waits for order confirmation before proceeding
- **Timeout Protection**: Automatic trade termination after 5 minutes
- **Error Recovery**: Graceful handling of connection issues and failed orders

## 📋 Prerequisites

- **Python 3.8 or higher**
- **Interactive Brokers Account** with TWS or IB Gateway
- **Active Market Data Subscription** (for real-time quotes)
- **Windows OS** (for audio alerts and some keyboard functionality)

## 🚀 Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/ibkr-trading-bot.git
cd ibkr-trading-bot
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Interactive Brokers

#### TWS Configuration
1. Open Trader Workstation (TWS)
2. Navigate to: **File > Global Configuration > API > Settings**
3. Enable:
   - ✅ Enable ActiveX and Socket Clients
   - ✅ Allow connections from localhost only
   - ✅ Read-Only API
4. Socket Port: **7496** (paper trading: 7497)
5. Click **OK** and restart TWS

#### IB Gateway Configuration
1. Launch IB Gateway
2. Configure API settings (same as above)
3. Default ports:
   - Live: 4001
   - Paper: 4002

### 5. Configure the Bot

Edit the `Config` class in `trading_bot.py`:

```python
class Config:
    # IB Connection
    IB_HOST = '127.0.0.1'
    IB_PORT = 7496  # 7497 for paper trading
    IB_CLIENT_ID = 1
    
    # Trading Parameters
    MAX_REENTRIES = 5
    TIMEOUT_MINUTES = 5
    STOP_LOSS_PCT = 0.975  # 2.5% stop loss
    
    # Position Sizing
    MIN_POSITION_SIZE = 3
    POSITION_CAPITAL = 30  # Dollar amount per position
```

## 💻 Usage

### Starting the Bot

```bash
python trading_bot.py
```

You should see the DEADHAND splash screen and connection confirmation.

### Executing a Trade

1. **Copy the stock symbol** to your clipboard (e.g., `AAPL`)
2. Bot will detect the symbol paste
3. **Copy the entry price** to your clipboard (e.g., `150.25`)
4. Bot automatically:
   - Calculates position size
   - Places limit buy order (2% above entry)
   - Sets up P&L monitoring
   - Manages the position through its lifecycle

### Emergency Controls

| Hotkey | Action |
|--------|--------|
| `Ctrl+Shift+X` | Clear clipboard (cancel current symbol) |
| `Ctrl+C` | Stop the bot |

### Trade Lifecycle

```
Entry → Fill → Stop Loss Active → 
  ├─ Hit 5% profit → Set Take Profits (33%, 66%, 99%)
  │   ├─ 33% TP Hit → Continue with remaining
  │   ├─ 66% TP Hit → Continue with remaining
  │   └─ 99% TP Hit → Trade Complete
  │
  └─ Stop Loss Hit → Reentry Order
      ├─ Reentry Fill → Restart Cycle
      └─ Max Reentries → Trade Complete
```

## 📊 State Machine

The bot operates through a sophisticated state machine:

| State | Description | Actions |
|-------|-------------|---------|
| `IN_TRADE_PNL_U5` | In trade, P&L under 5% | Stop loss active |
| `IN_TRADE_PNL_O5` | P&L over 5% | Set all take profits |
| `IN_TRADE_PNL_O33` | P&L over 33% | Monitor 66% TP |
| `IN_TRADE_PNL_O66` | P&L over 66% | Monitor 99% TP |
| `IN_TRADE_PNL_O99` | P&L over 99% | Trade complete |
| `STOPPED_OUT` | Stop loss triggered | Evaluate reentry |
| `WAITING_REENTRY` | Awaiting reentry fill | Monitor timeout |
| `TRADE_COMPLETE` | Trade finished | Cleanup |

## 📁 Project Structure

```
ibkr-trading-bot/
├── trading_bot.py          # Main trading bot script
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── LICENSE                # MIT License
├── .gitignore            # Git ignore rules
├── examples/
│   └── example_usage.md   # Usage examples
└── bot_logs/             # Log files (auto-created)
    └── trading_bot.log   # Execution log
```

## 🔧 Configuration Options

### Position Sizing Strategy

The bot uses dynamic position sizing:

```python
# Example: $30 position capital, $10 stock price
position_size = int(30 / 10) = 3 shares

# Example: $30 position capital, $50 stock price
# Below minimum, use MIN_POSITION_SIZE
position_size = 3 shares (minimum)
```

### Take Profit Levels

Customize profit targets:
- **TP1 (33%)**: 1/3 of position at 33% profit
- **TP2 (66%)**: 1/2 of remaining at 66% profit  
- **TP3 (99%)**: Final portion at 99% profit

### Stop Loss Protection

- **Initial**: 2.5% below entry price
- **Behavior**: Cancelled when profit exceeds 5%
- **Reactivated**: If profit falls back under 5%

## 📈 Performance Tracking

All trades are logged to `bot_logs/trading_bot.log`:

```
2024-02-13 09:30:15 - INFO - [AAPL] Order filled: 10 @ 150.25
2024-02-13 09:30:20 - INFO - [AAPL] PnL monitoring active - $5.50 (3.66%)
2024-02-13 09:35:42 - INFO - [AAPL] State change: IN_TRADE_PNL_U5 -> IN_TRADE_PNL_O5
2024-02-13 09:36:10 - INFO - [AAPL] Take profit 33% placed: 3 @ 199.83
```

## ⚠️ Risk Disclaimer

**This bot is for educational purposes only.**

- Trading involves substantial risk of loss
- Past performance does not guarantee future results
- Only trade with capital you can afford to lose
- Test thoroughly in paper trading before using real money
- The author is not responsible for any financial losses

## 🐛 Troubleshooting

### Connection Issues

**Problem**: Bot can't connect to IB
```
Solution:
1. Ensure TWS/IB Gateway is running
2. Check API settings are enabled
3. Verify port numbers match
4. Restart TWS/Gateway
```

### Order Rejection

**Problem**: Orders are rejected
```
Solution:
1. Check account has sufficient buying power
2. Verify market is open (or use outsideRth=True)
3. Ensure stock is not restricted
4. Check for duplicate orders
```

### P&L Monitoring Fails

**Problem**: P&L data not received
```
Solution:
1. Wait up to 60 seconds for initial data
2. Check you have market data subscription
3. Verify position was actually filled
4. Review logs for error messages
```

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [ib_insync](https://github.com/erdewit/ib_insync) - Excellent IB API wrapper
- [pyperclip](https://github.com/asweigart/pyperclip) - Cross-platform clipboard utilities
- [keyboard](https://github.com/boppreh/keyboard) - Global hotkey support

## 📧 Contact

Mail: calistersmasombo7@gmail.com

Upwork: https://upwork.com/freelancers/~01287a98d9ca2d5334

Project Link: [https://github.com/calisters/ibkr-trading-bot](https://github.com/calisters/ibkr-trading-bot)

---

⭐ If you find this project useful, please consider giving it a star!
