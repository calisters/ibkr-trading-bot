# Quick Start Guide - IBKR Trading Bot

## 5-Minute Setup

### Step 1: Prerequisites Check
- [ ] Python 3.8+ installed (`python --version`)
- [ ] Interactive Brokers account (paper or live)
- [ ] TWS or IB Gateway downloaded and installed

### Step 2: Install Bot
```bash
# Clone repository
git clone https://github.com/calisters/ibkr-trading-bot.git
cd ibkr-trading-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure IB

**In TWS/Gateway:**
1. File → Global Configuration → API → Settings
2. ✅ Enable ActiveX and Socket Clients
3. ✅ Allow connections from localhost
4. Port: 7496 (live) or 7497 (paper)
5. OK → Restart TWS

### Step 4: Test Connection
```bash
# Start TWS/Gateway first, then:
python trading_bot.py
```

You should see:
```
Connecting to Interactive Brokers...
Connected to IB successfully!
```

### Step 5: First Trade (Paper Account!)
1. **Copy symbol**: `AAPL` (Ctrl+C)
2. Bot detects paste
3. **Copy price**: `150.00`
4. Bot executes trade automatically!

Watch the terminal for status updates.

## Quick Reference

### Hotkeys
| Key | Action |
|-----|--------|
| `Ctrl+Shift+X` | Clear clipboard |
| `Ctrl+C` | Stop bot |

### File Locations
- **Logs**: `bot_logs/trading_bot.log`
- **Config**: `trading_bot.py` (Config class)

### Common Issues

**Can't connect?**
→ Check TWS is running, API enabled, correct port

**Order rejected?**
→ Check buying power, market hours, stock restrictions

**P&L not updating?**
→ Wait 60s, check market data subscription

## Next Steps

1. ✅ Test in paper account thoroughly
2. 📖 Read full [README.md](README.md)
3. 📊 Review [examples/example_usage.md](examples/example_usage.md)
4. ⚙️ Customize `Config` class for your strategy
5. 🚀 Use with [Scanner](../ibkr-scanner/) for best results

## Need Help?

- 📖 Full documentation: [README.md](README.md)
- 💬 Issues: [GitHub Issues](https://github.com/calisters/ibkr-trading-bot/issues)
- 📧 Contact: calistersmasombo7@gmail.com

---

**⚠️ IMPORTANT**: Always test with paper account before using real money!
