"""
IBKR Momentum Trading Bot - DEADHAND v2.0
Clipboard-based tactical execution interface for Interactive Brokers

Author: Calisters
Repository: https://github.com/calisters/ibkr-trading-bot
"""

import asyncio
import logging
import pyperclip
import time
import os
from ib_insync import *
from datetime import datetime, timedelta
import keyboard
from typing import Dict, List
import threading
import colorama
from colorama import Fore, Style
import functools

colorama.init()

# Force immediate print output
print = functools.partial(print, flush=True)


class Config:
    """Configuration settings for the trading bot"""
    # Logging
    LOG_DIR = "bot_logs"
    LOG_FILE = "trading_bot.log"
    
    # IB Connection
    IB_HOST = '127.0.0.1'
    IB_PORT = 7496
    IB_CLIENT_ID = 1
    
    # Trading Parameters
    MAX_REENTRIES = 5
    TIMEOUT_MINUTES = 5
    STOP_LOSS_PCT = 0.975  # 2.5% stop loss
    ENTRY_LIMIT_PCT = 1.02  # 2% above entry for limit order
    
    # Position Sizing (customize based on your risk tolerance)
    MIN_POSITION_SIZE = 3
    POSITION_CAPITAL = 30  # Dollar amount to use for position sizing
    
    # Take Profit Levels
    TP_33_MULTIPLIER = 1.33  # 33% profit target
    TP_66_MULTIPLIER = 1.66  # 66% profit target
    TP_99_MULTIPLIER = 1.99  # 99% profit target
    
    # PnL Thresholds (%)
    PNL_THRESHOLD_5 = 5
    PNL_THRESHOLD_33 = 33
    PNL_THRESHOLD_66 = 66
    PNL_THRESHOLD_99 = 99


# Setup logging
os.makedirs(Config.LOG_DIR, exist_ok=True)
log_path = os.path.join(Config.LOG_DIR, Config.LOG_FILE)
logging.basicConfig(
    filename=log_path,
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


def splash_screen():
    """Display startup banner"""
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\033[31m" + r"""
    -----------------------------------------------------------------------------------------------------
    |                                                                                                   |
    |    ██████╗    ███████╗   █████╗   ██████╗   ██╗  ██╗   █████╗   ███╗   ██╗  ██████╗     ███████║  |
    |    ██╔══██╗   ██╔════╝  ██╔══██╗  ██╔══██╗  ██║  ██║  ██╔══██╗  ████╗  ██║  ██╔══██╗    ╚════██║  |
    |    ██║  ██║   █████╗    ███████║  ██║  ██║  ███████║  ███████║  ██╔██╗ ██║  ██║  ██║    ███████║  |
    |    ██║  ██║   ██╔══╝    ██╔══██║  ██║  ██║  ██╔══██║  ██╔══██║  ██║╚██╗██║  ██║  ██║    ██╔════╝  |
    |    ██████╔╝   ███████╗  ██║  ██║  ██████╔╝  ██║  ██║  ██║  ██║  ██║ ╚████║  ██████╔╝    ███████╗  |
    |    ╚═════╝    ╚══════╝  ╚═╝  ╚═╝  ╚═════╝   ╚═╝  ╚═╝  ╚═╝  ╚═╝  ╚═╝  ╚═══╝  ╚═════╝     ╚══════╝  |
    |                                                                                                   |
    |                                       D E A D H A N D  v2.0                                       |
    |                                Tactical Execution Interface Launched!!                            |
    -----------------------------------------------------------------------------------------------------
    """ + "\033[0m")
    time.sleep(0.01)


class ClipboardClearedException(Exception):
    """Exception raised when clipboard is cleared during input"""
    pass


class TradeState:
    """Trading state machine states"""
    IN_TRADE_PNL_U5 = "IN_TRADE_PNL_U5"      # In trade, PnL under 5%
    STOPPED_OUT = "STOPPED_OUT"               # Stop loss hit
    WAITING_REENTRY = "WAITING_REENTRY"       # Waiting for reentry trigger
    IN_TRADE_PNL_O5 = "IN_TRADE_PNL_O5"      # In trade, PnL over 5%
    IN_TRADE_PNL_O33 = "IN_TRADE_PNL_O33"    # In trade, PnL over 33%
    IN_TRADE_PNL_O66 = "IN_TRADE_PNL_O66"    # In trade, PnL over 66%
    IN_TRADE_PNL_O99 = "IN_TRADE_PNL_O99"    # In trade, PnL over 99%
    TRADE_COMPLETE = "TRADE_COMPLETE"         # Trade finished


class OrderManager:
    """Global order manager for emergency operations"""
    
    def __init__(self):
        self.active_traders: Dict[str, 'StockTrader'] = {}
        self.hotkey_active = False
    
    def register_trader(self, trader: 'StockTrader'):
        """Register active trader"""
        self.active_traders[trader.symbol] = trader
    
    def unregister_trader(self, symbol: str):
        """Unregister completed trader"""
        if symbol in self.active_traders:
            del self.active_traders[symbol]
    
    def setup_emergency_hotkeys(self):
        """Setup keyboard hotkeys for emergency operations"""
        keyboard.add_hotkey('ctrl+shift+x', self.clear_clipboard_symbol)
    
    def clear_clipboard_symbol(self):
        """Emergency clipboard clear to stop processing current symbol"""
        if self.hotkey_active:
            return
        self.hotkey_active = True
        try:
            print("\n\t=== CLEARING CLIPBOARD SYMBOL ===")
            pyperclip.copy("")
            print("\tClipboard cleared - waiting for new symbol...")
        except Exception as e:
            print(f"\tClipboard clear error: {e}")
        finally:
            self.hotkey_active = False


# Global instances
order_manager = OrderManager()
tracked_symbols = set()


class StockTrader:
    """
    Individual stock trader managing a single position's lifecycle
    
    Implements a state machine for trade management:
    - Entry with limit order
    - Stop loss protection
    - Multi-level take profits (33%, 66%, 99%)
    - Reentry logic after stop-out
    - Real-time P&L monitoring
    """
    
    def __init__(self, ib: IB, symbol: str, entry_price: float, capital: float, 
                 price_precision: int, position: int):
        self.ib = ib
        self.symbol = symbol
        self.entry_price = entry_price
        self.capital = capital
        self.contract = Stock(symbol, 'SMART', 'USD')
        
        # State management
        self.state = None
        self.previous_states = []
        
        # Position tracking
        self.position_size = position
        self.live_position = 0
        self.fill_price = None
        self.exit_fill_price = 0
        self.total_exit_filled = 0
        
        # P&L tracking
        self.unrealized_pnl = 0
        self.unrealized_pnl_pct = 0
        self.last_pnl_update_time = None
        self.pnl_obj = None
        self.account = None
        
        # Orders
        self.initial_order = None
        self.stop_loss_order = None
        self.reentry_order = None
        self.take_profit_33 = None
        self.take_profit_66 = None
        self.take_profit_99 = None
        
        # Take profit fill tracking
        self.tp33_filled_handled = False
        self.tp66_filled_handled = False
        self.tp99_filled_handled = False
        
        # Timing
        self.start_time = datetime.now()
        self.timeout_duration = timedelta(minutes=Config.TIMEOUT_MINUTES)
        
        # Reentry management
        self.reentry_count = 0
        self.max_reentries = Config.MAX_REENTRIES
        
        # Precision
        self.price_precision = price_precision
        
        # Tracking key
        self.symbol_price_key = (symbol, entry_price)
        
        # Futures for async coordination
        self.order_futures = {}
        self.state_future = None
        
        # Register with global manager
        order_manager.register_trader(self)
        
        logging.info(f"StockTrader initialized for {symbol} at {entry_price}")
        print(f"\t[{symbol}] Initialized trader - Position size: {self.position_size}")
    
    def round_price(self, price: float) -> float:
        """Round price based on value (2 decimals for > $1, 4 for < $1)"""
        if price >= 1.0:
            return round(price, 2)
        else:
            return round(price, 4)
    
    def get_live_orders(self) -> List[Order]:
        """Get all currently active orders"""
        live_orders = []
        orders = [self.initial_order, self.stop_loss_order, self.reentry_order,
                 self.take_profit_33, self.take_profit_66, self.take_profit_99]
        for order in orders:
            if order and order.orderStatus.status in ['PreSubmitted', 'Submitted']:
                live_orders.append(order)
        return live_orders
    
    def is_order_cancelled(self, order) -> bool:
        """Check if order was cancelled"""
        return order and order.orderStatus.status == 'Cancelled'
    
    def is_order_live(self, order) -> bool:
        """Check if order is currently active"""
        return order and order.orderStatus.status in ['PreSubmitted', 'Submitted']
    
    async def setup_pnl_monitoring(self):
        """Setup real-time P&L monitoring for the position"""
        try:
            self.account = self.ib.wrapper.accounts[0]
            self.pnl_obj = self.ib.reqPnLSingle(
                self.account, 
                modelCode='', 
                conId=self.contract.conId
            )
            self.ib.pnlSingleEvent += self.on_pnl_update
            
            logging.info(f"[{self.symbol}] PnL monitoring requested")
            print(f"\t[{self.symbol}] Waiting for PnL data...")
            
            pnl_received = await self.wait_for_valid_pnl_data(timeout=60)
            if pnl_received:
                logging.info(
                    f"[{self.symbol}] PnL monitoring setup complete - "
                    f"Initial PnL: ${self.unrealized_pnl:.2f} ({self.unrealized_pnl_pct:.2f}%)"
                )
                print(
                    f"\t[{self.symbol}] PnL monitoring active - "
                    f"${self.unrealized_pnl:.2f} ({self.unrealized_pnl_pct:.2f}%)"
                )
                return True
            else:
                logging.error(f"[{self.symbol}] PnL monitoring setup failed - no data received")
                print(f"\t[{self.symbol}] PnL monitoring failed - no data received")
                return False
        except Exception as e:
            logging.error(f"[{self.symbol}] PnL monitoring setup error: {e}")
            print(f"\t[{self.symbol}] PnL monitoring error: {e}")
            return False
    
    async def wait_for_valid_pnl_data(self, timeout: int = 60) -> bool:
        """Wait for initial P&L data to arrive"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            await asyncio.sleep(0.5)
            if self.last_pnl_update_time and self.unrealized_pnl is not None:
                if await self.validate_pnl_data():
                    return True
        return False
    
    async def validate_pnl_data(self) -> bool:
        """Validate P&L data is reasonable"""
        try:
            if self.live_position == 0 or not self.fill_price:
                return False
            
            cost_basis = self.live_position * self.fill_price
            if cost_basis <= 0:
                return False
            
            calculated_pct = (self.unrealized_pnl / cost_basis) * 100
            if abs(calculated_pct - self.unrealized_pnl_pct) > 5:
                logging.warning(
                    f"[{self.symbol}] PnL mismatch - "
                    f"Reported: {self.unrealized_pnl_pct:.2f}%, "
                    f"Calculated: {calculated_pct:.2f}%"
                )
            return True
        except Exception as e:
            logging.error(f"[{self.symbol}] PnL validation error: {e}")
            return False
    
    def on_pnl_update(self, pnl):
        """Callback for P&L updates"""
        if pnl.conId == self.contract.conId:
            self.unrealized_pnl = pnl.unrealizedPnL or 0
            self.last_pnl_update_time = time.time()
            
            if self.live_position > 0 and self.fill_price:
                cost_basis = self.live_position * self.fill_price
                self.unrealized_pnl_pct = (
                    (self.unrealized_pnl / cost_basis) * 100 
                    if cost_basis > 0 else 0
                )
            
            logging.debug(
                f"[{self.symbol}] PnL update: "
                f"${self.unrealized_pnl:.2f} ({self.unrealized_pnl_pct:.2f}%)"
            )
            
            # Trigger state machine check
            if hasattr(self, 'state_future') and self.state_future and not self.state_future.done():
                self.state_future.set_result(True)
    
    async def get_actual_position(self) -> int:
        """Get actual position from broker"""
        try:
            positions = self.ib.positions()
            for pos in positions:
                if pos.contract.symbol == self.symbol:
                    return int(pos.position)
            return 0
        except Exception as e:
            logging.error(f"[{self.symbol}] Error getting actual position: {e}")
            print(f"\t[{self.symbol}] Error getting actual position: {e}")
            return 0
    
    async def check_position_integrity(self) -> bool:
        """Verify tracked position matches broker position"""
        actual_pos = await self.get_actual_position()
        position_discrepancy = abs(actual_pos - self.live_position)
        
        if position_discrepancy > 0 and actual_pos == 0:
            logging.info(
                f"[{self.symbol}] Position manually closed - "
                f"tracked: {self.live_position}, actual: {actual_pos}"
            )
            print(f"\t[{self.symbol}] Position manually closed - ending trade")
            self.live_position = 0
            await self.set_state(TradeState.TRADE_COMPLETE)
            return False
        elif position_discrepancy > self.live_position * 0.1:
            logging.warning(
                f"[{self.symbol}] Position discrepancy - "
                f"tracked: {self.live_position}, actual: {actual_pos}"
            )
            print(
                f"\t[{self.symbol}] Position discrepancy detected - "
                f"tracked: {self.live_position}, actual: {actual_pos}"
            )
            self.live_position = actual_pos
        
        return True
    
    async def submit_initial_buy(self):
        """Submit initial buy order"""
        try:
            limit_price = self.round_price(self.entry_price * Config.ENTRY_LIMIT_PCT)
            initial_order = LimitOrder(
                action='BUY',
                totalQuantity=self.position_size,
                lmtPrice=limit_price,
                tif='GTC',
                outsideRth=True
            )
            
            self.initial_order = self.ib.placeOrder(self.contract, initial_order)
            trade = self.initial_order
            
            logging.info(
                f"[{self.symbol}] Initial buy order placed: "
                f"{self.position_size} @ {limit_price}"
            )
            print(f"\t[{self.symbol}] BUY order placed: {self.position_size} @ {limit_price}")
            
            await self.wait_for_fill(trade)
        except Exception as e:
            logging.error(f"[{self.symbol}] Initial buy error: {e}")
            print(f"\t[{self.symbol}] Initial buy failed: {e}")
            await self.set_state(TradeState.TRADE_COMPLETE)
    
    async def wait_for_fill(self, trade):
        """Wait for order to fill"""
        while not trade.isDone():
            await asyncio.sleep(0.1)
        
        if trade.orderStatus.status == 'Filled':
            fills = trade.fills
            if fills:
                total_filled = sum(fill.execution.shares for fill in fills)
                avg_price = sum(
                    fill.execution.price * fill.execution.shares 
                    for fill in fills
                ) / total_filled
                
                self.live_position = total_filled
                self.fill_price = self.round_price(avg_price)
                
                logging.info(f"[{self.symbol}] Order filled: {total_filled} @ {self.fill_price}")
                print(f"\t[{self.symbol}] FILLED: {total_filled} @ {self.fill_price}")
                
                pnl_ready = await self.setup_pnl_monitoring()
                if pnl_ready:
                    await self.set_state(TradeState.IN_TRADE_PNL_U5)
                else:
                    logging.error(f"[{self.symbol}] PnL monitoring failed - cannot proceed")
                    print(f"\t[{self.symbol}] PnL monitoring failed - trade aborted")
                    await self.set_state(TradeState.TRADE_COMPLETE)
        else:
            logging.warning(f"[{self.symbol}] Order not filled: {trade.orderStatus.status}")
            print(f"\t[{self.symbol}] Order failed: {trade.orderStatus.status}")
            await self.set_state(TradeState.TRADE_COMPLETE)
    
    async def place_stop_loss(self):
        """Place stop loss order"""
        if self.live_position > 0:
            try:
                stop_price = self.round_price(self.fill_price * Config.STOP_LOSS_PCT)
                lmt_price = self.round_price(self.fill_price * 0.95)
                
                stop_loss_order = StopLimitOrder(
                    action='SELL',
                    totalQuantity=self.live_position,
                    stopPrice=stop_price,
                    lmtPrice=lmt_price,
                    tif='GTC',
                    outsideRth=True
                )
                
                self.stop_loss_order = self.ib.placeOrder(self.contract, stop_loss_order)
                await asyncio.sleep(0.22)
                
                while self.stop_loss_order.orderStatus.status not in ('PreSubmitted', 'Submitted', 'Filled'):
                    await asyncio.sleep(0.11)
                
                if self.stop_loss_order.orderStatus.status in ['PreSubmitted', 'Submitted']:
                    logging.info(
                        f"[{self.symbol}] Stop loss placed: "
                        f"{self.live_position} @ {stop_price}"
                    )
                    print(f"\t[{self.symbol}] STOP LOSS set @ {stop_price}")
                    return True
                else:
                    logging.error(
                        f"[{self.symbol}] Stop loss failed: "
                        f"{self.stop_loss_order.orderStatus.status}"
                    )
                    print(f"\t[{self.symbol}] Stop loss failed")
                    return False
            except Exception as e:
                logging.error(f"[{self.symbol}] Stop loss error: {e}")
                print(f"\t[{self.symbol}] Stop loss error: {e}")
                return False
        return True
    
    async def place_take_profit_33(self):
        """Place 33% take profit order"""
        if not self.is_order_live(self.take_profit_33):
            if self.live_position > self.position_size * 0.96:
                try:
                    tp_price = self.round_price(self.fill_price * Config.TP_33_MULTIPLIER)
                    tp_size = max(1, self.position_size // 3)
                    
                    take_profit_33 = LimitOrder(
                        action='SELL',
                        totalQuantity=tp_size,
                        lmtPrice=tp_price,
                        tif='GTC',
                        outsideRth=True
                    )
                    
                    self.take_profit_33 = self.ib.placeOrder(self.contract, take_profit_33)
                    
                    while self.take_profit_33.orderStatus.status not in ('PreSubmitted', 'Submitted', 'Filled'):
                        await asyncio.sleep(0.11)
                    
                    logging.info(
                        f"[{self.symbol}] Take profit 33% placed: "
                        f"{tp_size} @ {tp_price}"
                    )
                    print(f"\t[{self.symbol}] TP 33% set: {tp_size} @ {tp_price}")
                    return True
                except Exception as e:
                    logging.error(f"[{self.symbol}] TP 33% error: {e}")
                    print(f"\t[{self.symbol}] TP 33% error: {e}")
                    return False
        return True
    
    async def place_take_profit_66(self):
        """Place 66% take profit order"""
        if not self.is_order_live(self.take_profit_66):
            if self.live_position > self.position_size * 0.63:
                try:
                    tp_price = self.round_price(self.fill_price * Config.TP_66_MULTIPLIER)
                    first_third = max(1, self.position_size // 3)
                    tp_size = max(1, (self.position_size - first_third) // 2)
                    
                    take_profit_66 = LimitOrder(
                        action='SELL',
                        totalQuantity=tp_size,
                        lmtPrice=tp_price,
                        tif='GTC',
                        outsideRth=True
                    )
                    
                    self.take_profit_66 = self.ib.placeOrder(self.contract, take_profit_66)
                    
                    while self.take_profit_66.orderStatus.status not in ('PreSubmitted', 'Submitted', 'Filled'):
                        await asyncio.sleep(0.11)
                    
                    logging.info(
                        f"[{self.symbol}] Take profit 66% placed: "
                        f"{tp_size} @ {tp_price}"
                    )
                    print(f"\t[{self.symbol}] TP 66% set: {tp_size} @ {tp_price}")
                    return True
                except Exception as e:
                    logging.error(f"[{self.symbol}] TP 66% error: {e}")
                    print(f"\t[{self.symbol}] TP 66% error: {e}")
                    return False
        return True
    
    async def place_take_profit_99(self):
        """Place 99% take profit order"""
        if not self.is_order_live(self.take_profit_99):
            if self.live_position > self.position_size * 0.30:
                try:
                    tp_price = self.round_price(self.fill_price * Config.TP_99_MULTIPLIER)
                    first_third = max(1, self.position_size // 3)
                    second_third = max(1, (self.position_size - first_third) // 2)
                    tp_size = self.position_size - first_third - second_third
                    
                    take_profit_99 = LimitOrder(
                        action='SELL',
                        totalQuantity=tp_size,
                        lmtPrice=tp_price,
                        tif='GTC',
                        outsideRth=True
                    )
                    
                    self.take_profit_99 = self.ib.placeOrder(self.contract, take_profit_99)
                    
                    while self.take_profit_99.orderStatus.status not in ('PreSubmitted', 'Submitted', 'Filled'):
                        await asyncio.sleep(0.11)
                    
                    logging.info(
                        f"[{self.symbol}] Take profit 99% placed: "
                        f"{tp_size} @ {tp_price}"
                    )
                    print(f"\t[{self.symbol}] TP 99% set: {tp_size} @ {tp_price}")
                    return True
                except Exception as e:
                    logging.error(f"[{self.symbol}] TP 99% error: {e}")
                    print(f"\t[{self.symbol}] TP 99% error: {e}")
                    return False
        return True
    
    async def place_reentry_order(self):
        """Place reentry order after stop-out"""
        if not self.is_order_live(self.reentry_order):
            if datetime.now() - self.start_time > self.timeout_duration:
                logging.info(f"[{self.symbol}] Reentry timeout elapsed")
                print(f"\t[{self.symbol}] Reentry timeout - trade complete")
                await self.set_state(TradeState.TRADE_COMPLETE)
                return False
            
            try:
                stop_price = self.round_price(self.fill_price)
                limit_price = self.round_price(stop_price * 1.04)
                
                reentry_order = StopLimitOrder(
                    action='BUY',
                    totalQuantity=self.position_size,
                    stopPrice=stop_price,
                    lmtPrice=limit_price,
                    tif='GTC',
                    outsideRth=True
                )
                
                self.reentry_order = self.ib.placeOrder(self.contract, reentry_order)
                
                while self.reentry_order.orderStatus.status not in ('PreSubmitted', 'Submitted', 'Filled'):
                    await asyncio.sleep(0.11)
                
                logging.info(
                    f"[{self.symbol}] Reentry order placed: "
                    f"{self.position_size} @ {stop_price}"
                )
                print(f"\t[{self.symbol}] REENTRY order set: {self.position_size} @ {stop_price}")
                return True
            except Exception as e:
                logging.error(f"[{self.symbol}] Reentry order error: {e}")
                print(f"\t[{self.symbol}] Reentry order error: {e}")
                return False
        return True
    
    async def cancel_order(self, order):
        """Cancel an active order"""
        if order and self.is_order_live(order):
            try:
                self.ib.cancelOrder(order.order)
                timeout = 5
                start = time.time()
                
                while self.is_order_live(order) and (time.time() - start) < timeout:
                    await asyncio.sleep(0.1)
                
                if not self.is_order_live(order):
                    logging.info(f"[{self.symbol}] Order cancelled successfully")
                    print(f"\t[{self.symbol}] Order cancelled")
                    return True
                else:
                    logging.warning(f"[{self.symbol}] Order cancellation timeout")
                    print(f"\t[{self.symbol}] Order cancellation timeout")
                    return False
            except Exception as e:
                logging.error(f"[{self.symbol}] Cancel order error: {e}")
                print(f"\t[{self.symbol}] Cancel order error: {e}")
                return False
        return True
    
    async def cancel_take_profits(self):
        """Cancel all take profit orders"""
        orders = [self.take_profit_33, self.take_profit_66, self.take_profit_99]
        for order in orders:
            await self.cancel_order(order)
    
    async def emergency_close_position(self):
        """Emergency market close of position"""
        if self.live_position > 0:
            try:
                await self.cancel_order(self.stop_loss_order)
                await self.cancel_take_profits()
                
                market_order = MarketOrder(
                    action='SELL',
                    totalQuantity=self.live_position
                )
                
                trade = self.ib.placeOrder(self.contract, market_order)
                
                logging.info(f"[{self.symbol}] Emergency close order placed")
                print(f"\t[{self.symbol}] EMERGENCY CLOSE - Market sell {self.live_position}")
                
                await self.set_state(TradeState.TRADE_COMPLETE)
            except Exception as e:
                logging.error(f"[{self.symbol}] Emergency close error: {e}")
                print(f"\t[{self.symbol}] Emergency close error: {e}")
    
    async def set_state(self, new_state: str):
        """Change trading state"""
        if self.state != new_state:
            if self.state:
                self.previous_states.append(self.state)
            old_state = self.state
            self.state = new_state
            
            logging.info(f"[{self.symbol}] State change: {old_state} -> {new_state}")
            print(f"\n\t[{self.symbol}] STATE: {new_state}")
            
            if self.state_future and not self.state_future.done():
                self.state_future.set_result(True)
    
    def came_from_higher_state(self) -> bool:
        """Check if previous state was a higher profit state"""
        if not self.previous_states:
            return False
        last_state = self.previous_states[-1]
        higher_states = [
            TradeState.IN_TRADE_PNL_O5,
            TradeState.IN_TRADE_PNL_O33,
            TradeState.IN_TRADE_PNL_O66,
            TradeState.IN_TRADE_PNL_O99
        ]
        return last_state in higher_states
    
    # ==================== STATE HANDLERS ====================
    
    async def handle_in_trade_pnl_u5(self):
        """Handle state: PnL under 5%"""
        print(f"\t[{self.symbol}] Managing position - PnL: {self.unrealized_pnl_pct:.2f}%")
        
        if self.came_from_higher_state():
            await self.cancel_take_profits()
            await self.place_stop_loss()
        else:
            await self.place_stop_loss()
        
        while self.state == TradeState.IN_TRADE_PNL_U5:
            self.state_future = asyncio.Future()
            try:
                await asyncio.wait_for(self.state_future, timeout=1.0)
            except asyncio.TimeoutError:
                pass
            
            # Check if stop loss filled
            if self.stop_loss_order and self.stop_loss_order.orderStatus.status == 'Filled':
                fills = self.stop_loss_order.fills
                if fills:
                    self.total_exit_filled = sum(fill.execution.shares for fill in fills)
                    avg_exit_price = sum(
                        fill.execution.price * fill.execution.shares 
                        for fill in fills
                    ) / self.total_exit_filled
                    self.exit_fill_price = self.round_price(avg_exit_price)
                    
                    logging.info(
                        f"[{self.symbol}] Stop Loss filled: "
                        f"{self.total_exit_filled} @ {self.exit_fill_price}"
                    )
                    print(
                        f"\t[{self.symbol}] Stop Loss filled: "
                        f"{self.total_exit_filled} @ {self.exit_fill_price}"
                    )
                
                self.live_position = 0
                await self.set_state(TradeState.STOPPED_OUT)
                break
            
            if not await self.check_position_integrity():
                break
            
            # Check for manual cancellation
            if self.is_order_cancelled(self.stop_loss_order):
                logging.info(f"[{self.symbol}] Stop loss manually cancelled - trade complete")
                print(f"\t[{self.symbol}] Stop loss manually cancelled - ending trade")
                await self.set_state(TradeState.TRADE_COMPLETE)
                break
            
            # Check for profit threshold
            if self.unrealized_pnl_pct > Config.PNL_THRESHOLD_5 and self.unrealized_pnl_pct < 100:
                await self.set_state(TradeState.IN_TRADE_PNL_O5)
                break
    
    async def handle_stopped_out(self):
        """Handle state: Stopped out"""
        print(f"\t[{self.symbol}] TOTAL EXIT FILLED: {self.total_exit_filled} @ {self.exit_fill_price}")
        
        if self.total_exit_filled < self.position_size:
            print(
                f"\tTotal exit filled: {self.total_exit_filled} "
                f"is less than original buy position: {self.position_size} shares"
            )
            print(f"\tSome profit levels were hit. Closing coroutine for {self.symbol}")
            await self.set_state(TradeState.TRADE_COMPLETE)
        else:
            if self.reentry_count >= self.max_reentries:
                print(
                    f"\t[{self.symbol}] Maximum reentries ({self.max_reentries}) "
                    f"reached - trade complete"
                )
                logging.info(f"[{self.symbol}] Maximum reentries reached, ending trade")
                await self.set_state(TradeState.TRADE_COMPLETE)
                return
            
            print(
                f"\t[{self.symbol}] Stopped out - preparing reentry "
                f"(attempt {self.reentry_count + 1}/{self.max_reentries})"
            )
            logging.info(
                f"[{self.symbol}] Position stopped out - "
                f"reentry attempt {self.reentry_count + 1}"
            )
            
            if await self.place_reentry_order():
                await self.set_state(TradeState.WAITING_REENTRY)
            else:
                await self.set_state(TradeState.TRADE_COMPLETE)
    
    async def handle_waiting_reentry(self):
        """Handle state: Waiting for reentry"""
        print(
            f"\t[{self.symbol}] Waiting for reentry... "
            f"(attempt {self.reentry_count + 1}/{self.max_reentries})"
        )
        
        while self.state == TradeState.WAITING_REENTRY:
            # Check timeout
            if datetime.now() - self.start_time > self.timeout_duration:
                await self.cancel_order(self.reentry_order)
                await self.set_state(TradeState.TRADE_COMPLETE)
                break
            
            # Check manual cancellation
            if self.is_order_cancelled(self.reentry_order):
                logging.info(f"[{self.symbol}] Reentry order manually cancelled - trade complete")
                print(f"\t[{self.symbol}] Reentry order manually cancelled - ending trade")
                await self.set_state(TradeState.TRADE_COMPLETE)
                break
            
            # Check if reentry filled
            if self.reentry_order and self.reentry_order.orderStatus.status == 'Filled':
                self.reentry_count += 1
                self.total_exit_filled = 0
                self.exit_fill_price = 0
                
                fills = [trade for trade in self.ib.trades() if trade == self.reentry_order]
                if fills:
                    trade = fills[0]
                    if trade.fills:
                        total_filled = sum(fill.execution.shares for fill in trade.fills)
                        avg_price = sum(
                            fill.execution.price * fill.execution.shares 
                            for fill in trade.fills
                        ) / total_filled
                        
                        self.live_position = total_filled
                        self.fill_price = self.round_price(avg_price)
                        
                        logging.info(
                            f"[{self.symbol}] Reentry #{self.reentry_count} filled: "
                            f"{total_filled} @ {self.fill_price}"
                        )
                        print(
                            f"\t[{self.symbol}] REENTRY #{self.reentry_count} FILLED: "
                            f"{total_filled} @ {self.fill_price}"
                        )
                        
                        self.stop_loss_order = None
                        await self.set_state(TradeState.IN_TRADE_PNL_U5)
                        break
            
            await asyncio.sleep(0.22)
    
    async def handle_in_trade_pnl_o5(self):
        """Handle state: PnL over 5%"""
        print(f"\t[{self.symbol}] Above 5% profit - setting take profits")
        
        await self.cancel_order(self.stop_loss_order)
        await self.place_take_profit_33()
        await self.place_take_profit_66()
        await self.place_take_profit_99()
        
        while self.state == TradeState.IN_TRADE_PNL_O5:
            self.state_future = asyncio.Future()
            try:
                await asyncio.wait_for(self.state_future, timeout=1.0)
            except asyncio.TimeoutError:
                pass
            
            # Check TP33 fill
            if (not self.tp33_filled_handled and 
                self.take_profit_33 and 
                self.take_profit_33.orderStatus.status == 'Filled'):
                fills = [trade for trade in self.ib.trades() if trade == self.take_profit_33]
                if fills and fills[0].fills:
                    filled_shares = sum(fill.execution.shares for fill in fills[0].fills)
                    self.live_position -= filled_shares
                    self.tp33_filled_handled = True
            
            if self.unrealized_pnl_pct > Config.PNL_THRESHOLD_33:
                await self.set_state(TradeState.IN_TRADE_PNL_O33)
                break
            
            if not await self.check_position_integrity():
                break
            
            if self.unrealized_pnl_pct < Config.PNL_THRESHOLD_5:
                await self.set_state(TradeState.IN_TRADE_PNL_U5)
                break
    
    async def handle_in_trade_pnl_o33(self):
        """Handle state: PnL over 33%"""
        print(
            f"\t[{self.symbol}] 33% take profit hit - "
            f"{self.live_position} shares remaining"
        )
        
        while self.state == TradeState.IN_TRADE_PNL_O33:
            self.state_future = asyncio.Future()
            try:
                await asyncio.wait_for(self.state_future, timeout=1.0)
            except asyncio.TimeoutError:
                pass
            
            # Check TP66 fill
            if (not self.tp66_filled_handled and 
                self.take_profit_66 and 
                self.take_profit_66.orderStatus.status == 'Filled'):
                fills = [trade for trade in self.ib.trades() if trade == self.take_profit_66]
                if fills and fills[0].fills:
                    filled_shares = sum(fill.execution.shares for fill in fills[0].fills)
                    self.live_position -= filled_shares
                    self.tp66_filled_handled = True
            
            if not await self.check_position_integrity():
                break
            
            if self.unrealized_pnl_pct > Config.PNL_THRESHOLD_66:
                await self.set_state(TradeState.IN_TRADE_PNL_O66)
                break
            
            if self.unrealized_pnl_pct < Config.PNL_THRESHOLD_33:
                await self.set_state(TradeState.IN_TRADE_PNL_O5)
                break
    
    async def handle_in_trade_pnl_o66(self):
        """Handle state: PnL over 66%"""
        print(
            f"\t[{self.symbol}] 66% take profit hit - "
            f"{self.live_position} shares remaining"
        )
        
        while self.state == TradeState.IN_TRADE_PNL_O66:
            self.state_future = asyncio.Future()
            try:
                await asyncio.wait_for(self.state_future, timeout=1.0)
            except asyncio.TimeoutError:
                pass
            
            # Check TP99 fill
            if (not self.tp99_filled_handled and 
                self.take_profit_99 and 
                self.take_profit_99.orderStatus.status == 'Filled'):
                fills = [trade for trade in self.ib.trades() if trade == self.take_profit_99]
                if fills and fills[0].fills:
                    filled_shares = sum(fill.execution.shares for fill in fills[0].fills)
                    self.live_position -= filled_shares
                    self.tp99_filled_handled = True
            
            if not await self.check_position_integrity():
                break
            
            if self.unrealized_pnl_pct > Config.PNL_THRESHOLD_99:
                await self.set_state(TradeState.IN_TRADE_PNL_O99)
                break
            
            if self.unrealized_pnl_pct < Config.PNL_THRESHOLD_66:
                await self.set_state(TradeState.IN_TRADE_PNL_O33)
                break
    
    async def handle_in_trade_pnl_o99(self):
        """Handle state: PnL over 99%"""
        print(f"\t[{self.symbol}] 99% take profit hit - trade complete!")
        logging.info(f"[{self.symbol}] Trade completed successfully")
        await self.set_state(TradeState.TRADE_COMPLETE)
    
    async def handle_trade_complete(self):
        """Handle state: Trade complete"""
        print(f"\t[{self.symbol}] Trade complete - cleaning up")
        logging.info(f"[{self.symbol}] Trade completed - final position: {self.live_position}")
        
        # Cancel all orders
        orders = [
            self.initial_order, self.stop_loss_order, self.reentry_order,
            self.take_profit_33, self.take_profit_66, self.take_profit_99
        ]
        for order in orders:
            await self.cancel_order(order)
        
        # Unregister from global manager
        order_manager.unregister_trader(self.symbol)
        
        # Remove from tracked symbols
        global tracked_symbols
        if self.symbol_price_key in tracked_symbols:
            tracked_symbols.remove(self.symbol_price_key)
            logging.info(f"[{self.symbol}] Removed {self.symbol_price_key} from tracked symbols")
            print(f"\t[{self.symbol}] Symbol/price cleared from tracking")
        
        print(f"\t[{self.symbol}] Trader shutdown complete")
    
    async def run_state_machine(self):
        """Run the trading state machine"""
        state_handlers = {
            TradeState.IN_TRADE_PNL_U5: self.handle_in_trade_pnl_u5,
            TradeState.STOPPED_OUT: self.handle_stopped_out,
            TradeState.WAITING_REENTRY: self.handle_waiting_reentry,
            TradeState.IN_TRADE_PNL_O5: self.handle_in_trade_pnl_o5,
            TradeState.IN_TRADE_PNL_O33: self.handle_in_trade_pnl_o33,
            TradeState.IN_TRADE_PNL_O66: self.handle_in_trade_pnl_o66,
            TradeState.IN_TRADE_PNL_O99: self.handle_in_trade_pnl_o99,
            TradeState.TRADE_COMPLETE: self.handle_trade_complete
        }
        
        while self.state != TradeState.TRADE_COMPLETE:
            if self.state in state_handlers:
                try:
                    await state_handlers[self.state]()
                except Exception as e:
                    logging.error(f"[{self.symbol}] State handler error in {self.state}: {e}")
                    print(f"\t[{self.symbol}] Error in {self.state}: {e}")
                    await self.set_state(TradeState.TRADE_COMPLETE)
            else:
                logging.error(f"[{self.symbol}] Unknown state: {self.state}")
                print(f"\t[{self.symbol}] Unknown state: {self.state}")
                await self.set_state(TradeState.TRADE_COMPLETE)
        
        logging.info(f"[{self.symbol}] State machine completed")
    
    async def start(self):
        """Start the trader"""
        try:
            await self.ib.qualifyContractsAsync(self.contract)
            await self.submit_initial_buy()
            await self.run_state_machine()
        except Exception as e:
            logging.error(f"[{self.symbol}] Start error: {e}")
            print(f"\t[{self.symbol}] Start error: {e}")
        finally:
            order_manager.unregister_trader(self.symbol)
            global tracked_symbols
            if hasattr(self, 'symbol_price_key') and self.symbol_price_key in tracked_symbols:
                tracked_symbols.remove(self.symbol_price_key)
                logging.info(
                    f"[{self.symbol}] Emergency cleanup: "
                    f"Removed {self.symbol_price_key} from tracked symbols"
                )
                print(f"\t[{self.symbol}] Emergency cleanup: Symbol/price cleared from tracking")


async def wait_for_clipboard_change(prompt, cast_func=str):
    """
    Wait for clipboard content to change
    
    Args:
        prompt: Message to display to user
        cast_func: Function to cast clipboard content (str or float)
    
    Returns:
        Clipboard content cast to appropriate type
    
    Raises:
        ClipboardClearedException: If clipboard is cleared during wait
    """
    print(prompt)
    last_value = pyperclip.paste().strip()
    
    while True:
        await asyncio.sleep(0.11)
        try:
            current = pyperclip.paste().strip()
            if current != last_value:
                if not current:
                    print("\t[!] Clipboard cleared - restarting sequence...")
                    raise ClipboardClearedException("Clipboard was cleared")
                print("\tNew clipboard paste")
                return cast_func(current)
        except ClipboardClearedException:
            raise
        except Exception as e:
            print(f"\tClipboard read error: {e}")
            last_value = ""
            continue


async def monitor_clipboard_and_spawn(ib):
    """
    Monitor clipboard for symbol/price pairs and spawn traders
    
    Workflow:
    1. Wait for symbol paste
    2. Wait for price paste
    3. Calculate position size
    4. Spawn StockTrader coroutine
    5. Repeat
    """
    global tracked_symbols
    active_traders = {}
    
    async def trader_wrapper(trader):
        """Wrapper to manage trader lifecycle"""
        nonlocal active_traders
        try:
            await trader.start()
        finally:
            if trader.symbol in active_traders:
                del active_traders[trader.symbol]
                print(f"\t[{trader.symbol}] Removed from active traders count")
    
    while True:
        try:
            # Get account capital
            capital = float(
                next(v.value for v in ib.accountValues() if v.tag == 'NetLiquidation')
            )
            print(f"\n\t=== Capital: ${capital:,.2f} ===")
            
            # Wait for symbol
            try:
                symbol = await wait_for_clipboard_change(
                    "\t>>> Paste SYMBOL into clipboard...", 
                    cast_func=str
                )
                symbol = symbol.strip().upper()
            except ClipboardClearedException:
                continue
            
            # Wait for price
            try:
                entry_price = await wait_for_clipboard_change(
                    f"\t>>> Now paste PRICE for {symbol} into clipboard...",
                    cast_func=float
                )
            except ClipboardClearedException:
                continue
            except ValueError as e:
                print(f"\t[!] Invalid price format: {e}")
                continue
            
            # Dynamic position sizing
            if int(Config.POSITION_CAPITAL // entry_price) < Config.MIN_POSITION_SIZE:
                position = Config.MIN_POSITION_SIZE
            else:
                position = int(Config.POSITION_CAPITAL // entry_price)
            
            # Check if already tracking this symbol/price
            if (symbol, entry_price) in tracked_symbols:
                print(f"\t[!] Already handling {symbol} at {entry_price}")
                continue
            
            tracked_symbols.add((symbol, entry_price))
            
            # Determine price precision
            entry_price_str = f"{entry_price:.10f}".rstrip('0').rstrip('.')
            price_precision = (
                len(entry_price_str.split('.')[-1]) 
                if '.' in entry_price_str else 0
            )
            
            # Create and spawn trader
            trader = StockTrader(
                ib, symbol, entry_price, capital, 
                price_precision, position
            )
            active_traders[symbol] = trader
            asyncio.create_task(trader_wrapper(trader))
            
            logging.info(f"Spawned coroutine for {symbol} at {entry_price}")
            print(f"\t[{symbol}] Trader spawned successfully")
            
            await asyncio.sleep(1)
            
        except Exception as e:
            logging.error(f"Clipboard monitor error: {e}")
            print(f"\tClipboard monitor error: {e}")
            await asyncio.sleep(1)


async def main():
    """Main entry point"""
    splash_screen()
    logging.info("Trading bot started")
    
    ib = IB()
    
    try:
        # Connect to IB
        print("\tConnecting to Interactive Brokers...")
        await ib.connectAsync(Config.IB_HOST, Config.IB_PORT, clientId=Config.IB_CLIENT_ID)
        print("\tConnected to IB successfully!")
        logging.info("Connected to IB")
        
        await asyncio.sleep(1.3)
        
        # Setup emergency hotkeys
        def setup_hotkeys():
            order_manager.setup_emergency_hotkeys()
        
        hotkey_thread = threading.Thread(target=setup_hotkeys, daemon=True)
        hotkey_thread.start()
        
        print("\n\t=== Emergency Hotkeys Active ===")
        print("\tCtrl+Shift+X: Clear clipboard symbol")
        print("\t================================\n")
        
        # Start clipboard monitoring
        await monitor_clipboard_and_spawn(ib)
        
    except Exception as e:
        logging.error(f"Main error: {e}")
        print(f"\tMain error: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\tDisconnected from IB")
            logging.info("Disconnected from IB")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\t\n=== Bot stopped by user ===")
        logging.info("Bot stopped by user")
    except Exception as e:
        print(f"\tFatal error: {e}")
        logging.error(f"Fatal error: {e}")
