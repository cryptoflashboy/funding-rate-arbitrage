from synthetix import *
from APICaller.Perennial.perennialCallerUtils import *
from GlobalUtils.globalUtils import *
from GlobalUtils.logger import *
from pubsub import pub
from PositionMonitor.Master.MasterPositionMonitorUtils import *
import sqlite3
from TxExecution.Perennial.PerennialPositionControllerUtils import get_positions_for_all_markets


class PerennialPositionMonitor():
    def __init__(self, db_path='trades.db'):
        self.db_path = db_path
        try:
            self.conn = sqlite3.connect(self.db_path)
        except Exception as e:
            logger.error(f"PerennialPositionMonitor - Error accessing the database: {e}")
            return None

    def get_open_position(self) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''SELECT * FROM trade_log WHERE open_close = 'Open' AND exchange = 'Perennial';''')
                open_position = cursor.fetchone()
                if open_position:
                    position_dict = get_dict_from_database_response(open_position)
                    return position_dict
                else:
                    logger.error("PerennialPositionMonitor - No open Perennial positions found with details")
                    return None

        except sqlite3.Error as sqe:
            logger.error(f"PerennialPositionMonitor - Database error while searching for open Perennial positions: {sqe}")
            return None

        except Exception as e:
            logger.error(f"PerennialPositionMonitor - Error while searching for open Perennial positions: {e}")
            return None


    def is_near_liquidation_price(self, position: dict) -> bool:
        try:
            percentage_from_liqiudation_price = get_percentage_away_from_liquidation_price(position)
            MAX_ALLOWABLE_PERCENTAGE_AWAY_FROM_LIQUIDATION_PRICE = float(os.getenv('MAX_ALLOWABLE_PERCENTAGE_AWAY_FROM_LIQUIDATION_PRICE'))
            if percentage_from_liqiudation_price < MAX_ALLOWABLE_PERCENTAGE_AWAY_FROM_LIQUIDATION_PRICE:
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"PerennialPositionMonitor - Error checking if near liquidation price for {position}: {e}")
            return False

    def get_funding_rate(self, position) -> float:
        try:
            symbol = position['symbol']
            market = self.client.perps.get_market_summary(market_name=symbol)
            
            if 'current_funding_rate' in market:
                funding_rate = float(market['current_funding_rate'])
                return funding_rate
            else:
                logger.error(f"PerennialPositionMonitor - Funding rate not found in market summary for symbol {symbol}.")
                return None 
            
        except Exception as e:
            logger.error(f"PerennialPositionMonitor - Error fetching funding rate for symbol {symbol}: {e}")
            return None

    def get_open_positions(self) -> list:
        try:
            positions = get_positions_for_all_markets()
            if len(positions) > 0:
                return positions
            else:
                return None

        except Exception as e:
            logger.error(f"PerennialPositionController - Failed to get open positions: {e}")
            return None

    def is_open_position(self) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''SELECT * FROM trade_log WHERE open_close = 'Open' AND exchange = 'Perennial';''')
                open_positions = cursor.fetchall()
                if open_positions:
                    return True
                else:
                    return False
        except Exception as e:
            logger.error(f"PerennialPositionMonitor - Error while searching for open Perennial positions:", {e})
            raise e