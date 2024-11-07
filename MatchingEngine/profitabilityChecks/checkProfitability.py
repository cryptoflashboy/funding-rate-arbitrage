from GlobalUtils.globalUtils import *
from GlobalUtils.logger import *
from TxExecution.Master.MasterPositionController import MasterPositionController
from MatchingEngine.profitabilityChecks.checkProfitabilityUtils import *
from GlobalUtils.MarketDirectories.SynthetixMarketDirectory import SynthetixMarketDirectory
from GlobalUtils.MarketDirectories.GMXMarketDirectory import GMXMarketDirectory
from MatchingEngine.profitabilityChecks.GMX.GMXCheckProfitabilityUtils import *
# from APICaller.HMX.HMXCallerUtils import *
# from MatchingEngine.profitabilityChecks.HMX.HMXCheckProfitabilityUtils import *
# from MatchingEngine.profitabilityChecks.Synthetix.SynthetixCheckProfitabilityUtils import *
from APICaller.ByBit.ByBitCaller import ByBitCaller
from gmx_python_sdk.scripts.v2.get.get_oracle_prices import OraclePrices
from APICaller.GMX.GMXCallerUtils import ARBITRUM_CONFIG_OBJECT
from APICaller.master.MasterUtils import get_target_exchanges
from MatchingEngine.profitabilityChecks.Perennial.PerennialProfitabilityChecks import *
import json
import os

class ProfitabilityChecker:
    def __init__(self):
        self.position_controller = MasterPositionController()
        self.bybit_caller = ByBitCaller()
        # self.okx_caller = OKXCaller()
        self.gmx_prices = {}
        self.gmx_open_interest = {}

        self.default_trade_duration = float(os.getenv('DEFAULT_TRADE_DURATION_HOURS'))
        self.default_trade_size_usd = float(os.getenv('DEFAULT_TRADE_SIZE_USD'))

    def find_most_profitable_opportunity(self, opportunities: list, is_demo: bool):
        try:
            trade_size_usd = self.default_trade_size_usd
            best_opportunity = None
            max_profit = 0
            opportunities_with_profit = []
            if 'GMX' in get_target_exchanges():
                self.gmx_prices = OraclePrices(chain=ARBITRUM_CONFIG_OBJECT.chain).get_recent_prices()
                self.gmx_open_interest = OpenInterest(ARBITRUM_CONFIG_OBJECT)._get_data_processing(self.gmx_prices)

            for opportunity in opportunities:
                symbol = opportunity['symbol']
                size_per_exchange = trade_size_usd / 2
                total_profit_usd = 0
                hours_to_neutralize_by_exchange = {}

                for role in ['long', 'short']:
                    exchange = opportunity[f'{role}_exchange']
                    time_to_neutralize = self.estimate_time_to_neutralize_funding_rate_for_exchange(
                        opportunity,
                        size_per_exchange,
                        exchange
                    )

                    if time_to_neutralize == None:
                        logger.error(f'CheckProfitability - NoneType returned while estimating time to neutralize rate.')
                        return None

                    if time_to_neutralize == "No Neutralization":
                        hours_to_neutralize_by_exchange[f'{role}_exchange'] = self.default_trade_duration
                    else:
                        time_period_hours = time_to_neutralize
                        hours_to_neutralize_by_exchange[f'{role}_exchange'] = time_period_hours
                        opportunity['trade_duration_estimate'] = time_to_neutralize

                pnl_dict = self.estimate_profit_for_time_period(hours_to_neutralize_by_exchange, trade_size_usd, opportunity)
                if not pnl_dict or pnl_dict['total_profit_loss'] == None:
                    logger.warning(f'CheckProfitability - No (or incomplete) Pnl data returned for symbol {symbol}')
                    continue

                total_profit_usd = float(pnl_dict['total_profit_loss'])
                opportunity['total_profit_usd'] = total_profit_usd
                opportunity['long_exchange_profit_usd'] = float(pnl_dict['long_exchange_profit_loss'])
                opportunity['short_exchange_profit_usd'] = float(pnl_dict['short_exchange_profit_loss'])
                opportunities_with_profit.append(opportunity)

                if total_profit_usd > max_profit:
                    max_profit = total_profit_usd
                    best_opportunity = opportunity

            opportunities_with_profit.sort(key=lambda x: x['total_profit_usd'], reverse=True)

            if is_demo:
                return opportunities_with_profit
            else:
                with open('OrderedOpportunities.json', 'w') as file:
                    json.dump(opportunities_with_profit, file, indent=4)
                return best_opportunity

        except Exception as e:
            logger.error(f'CheckProfitability - Failed to find most profitable opportunity. Error: {e}', exc_info=True)

    def estimate_profit_for_exchange(self, time_period_hours: float, size_usd: float, opportunity: dict, exchange: str) -> float:
        try:
            estimated_profit = None
            if exchange == 'Binance':
                estimated_profit = self.estimate_binance_profit(time_period_hours=time_period_hours, size_usd=size_usd, opportunity=opportunity)
                return estimated_profit
            elif exchange == 'Synthetix':
                estimated_profit = self.estimate_synthetix_profit(time_period_hours=time_period_hours, absolute_size_usd=size_usd, opportunity=opportunity)
                return estimated_profit
            elif exchange == 'GMX':
                estimated_profit = self.estimate_GMX_profit(time_period_hours=time_period_hours, absolute_size_usd=size_usd, opportunity=opportunity, open_interest=self.gmx_open_interest)
                return estimated_profit
            # elif exchange == 'HMX':
            #     estimated_profit = estimate_HMX_profit(time_period_hours=time_period_hours, size_usd=size_usd, opportunity=opportunity)
            #     return estimated_profit
            elif exchange == 'ByBit':
                estimated_profit = self.estimate_bybit_profit(time_period_hours=time_period_hours, size_usd=size_usd, opportunity=opportunity)
                return estimated_profit
            elif exchange == 'OKX':
                estimated_profit = self.estimate_okx_profit(time_period_hours=time_period_hours, size_usd=size_usd, opportunity=opportunity)
                return estimated_profit
            elif exchange == 'Perennial':
                estimated_profit = self.estimate_perennial_profit(time_period_hours=time_period_hours, size_usd=size_usd, opportunity=opportunity)
                return estimated_profit

            if not estimated_profit:
                return None

        except Exception as e:
            logger.error(f'CheckProfitability - Failed to estimate profit for exchange {exchange}, Error: {e}')
            return None

    def estimate_time_to_neutralize_funding_rate_for_exchange(self, opportunity: dict, size_usd: float, exchange: str):
        try:
            # if exchange == "HMX":
            #     time_to_neutralize = estimate_time_to_neutralize_funding_rate_hmx(opportunity, size_usd)
            #     if type(time_to_neutralize) == str:
            #         time_to_neutralize = self.default_trade_duration
            #         return time_to_neutralize
            #     else:
            #         return time_to_neutralize

            # if exchange == "Synthetix":
            #     time_to_neutralize = estimate_time_to_neutralize_funding_rate_synthetix(opportunity, absolute_size_usd=size_usd)
            #     if type(time_to_neutralize) == str:
            #         time_to_neutralize = self.default_trade_duration
            #         return time_to_neutralize
            #     else:
            #         return time_to_neutralize
            
            if exchange == "GMX":
                time_to_neutralize = estimate_time_to_neutralize_funding_rate_gmx(
                    opportunity, 
                    absolute_size_usd=size_usd, 
                    open_interest=self.gmx_open_interest
                    )

                if type(time_to_neutralize) == str:
                    time_to_neutralize = self.default_trade_duration
                    return time_to_neutralize
                else:
                    return time_to_neutralize

            elif exchange == "ByBit":
                return "No Neutralization"

            elif exchange == "Binance":
                return "No Neutralization"

            elif exchange == "OKX":
                return "No Neutralization"

        except Exception as e:
            logger.error(f'CheckProfitability - Failed to estimate profit for exchange {exchange}, Error: {e}')
            return None

    # def estimate_synthetix_profit(self, time_period_hours: float, absolute_size_usd: float, opportunity: dict) -> tuple:
    #     is_long: bool = opportunity['long_exchange'] == 'Synthetix'
    #     symbol = str(opportunity['symbol'])
    #     skew_usd: float = opportunity['long_exchange_skew_usd'] if is_long else opportunity['short_exchange_skew_usd']

    #     try:
    #         is_long = opportunity['long_exchange'] == 'Synthetix'

    #         size_usd = get_adjusted_size(absolute_size_usd, is_long)
    #         skew_usd_after_trade = skew_usd + size_usd
    #         opening_fee = SynthetixMarketDirectory.get_total_opening_fee(symbol, skew_usd, is_long, absolute_size_usd)
    #         closing_fee = SynthetixMarketDirectory.get_total_closing_fee(symbol, skew_usd_after_trade, is_long, absolute_size_usd)

    #         gas_fee_usd = 1
    #         premium = self.position_controller.synthetix.calculate_premium_usd(symbol, size_usd)

    #         total_funding = calculate_expected_funding_for_time_period_usd(
    #             opportunity,
    #             is_long,
    #             absolute_size_usd,
    #             time_period_hours
    #         )

            
    #         total_fees = (opening_fee + premium + gas_fee_usd + closing_fee)
    #         profit_after_fees = total_funding - total_fees

    #         return profit_after_fees

    #     except Exception as e:
    #         logger.error(f'CheckProfitability -  Error estimating Synthetix profit for {symbol}: Error: {e}')
    #         return None

    def estimate_binance_profit(self, time_period_hours: float, size_usd: float, opportunity: dict):
        try:
            symbol = opportunity['symbol']
            is_long = opportunity['long_exchange'] == 'Binance'
            funding_rate = opportunity['long_exchange_funding_rate_8hr'] if is_long else opportunity['short_exchange_funding_rate_8hr']
            current_block_number = get_base_block_number()
            size_usd = get_adjusted_size(size_usd, is_long)

            binance_funding_events = get_binance_funding_event_schedule(current_block_number)
            end_block_number = current_block_number + BLOCKS_PER_HOUR_BASE * time_period_hours

            total_profit_loss = 0
            for event_block in binance_funding_events:
                if current_block_number <= event_block <= end_block_number:
                    profit_loss_per_event = funding_rate * size_usd
                    if (is_long and funding_rate > 0) or (not is_long and funding_rate < 0):
                        profit_loss_per_event *= -1

                    total_profit_loss += profit_loss_per_event

            return total_profit_loss

        except Exception as e:
            logger.error(f'CheckProfitability - Error estimating Binance profit for {symbol}: {e}')
            return None

    def estimate_bybit_profit(self, time_period_hours: float, size_usd: float, opportunity: dict) -> float:
        try:
            symbol = opportunity['symbol'] + 'USDT'
            is_long = opportunity['long_exchange'] == 'ByBit'
            funding_rate = opportunity['long_exchange_funding_rate_8hr'] if is_long else opportunity['short_exchange_funding_rate_8hr']
            number_of_funding_events_in_time_period = self.bybit_caller.get_next_funding_events_for_time_period(symbol, time_period_hours)

            if is_long:
                if funding_rate > 0:
                    # rate positive, long
                    profit_loss_usd_per_event = size_usd * funding_rate
                    profit_loss_usd_per_event = -profit_loss_usd_per_event
                else:
                    # rate negative, long
                    profit_loss_usd_per_event = size_usd * abs(funding_rate)
            else:
                if funding_rate > 0:
                    # rate positive, short
                    profit_loss_usd_per_event = size_usd * funding_rate
                else:
                    # rate negative, short
                    profit_loss_usd_per_event = size_usd * abs(funding_rate)
                    profit_loss_usd_per_event = -profit_loss_usd_per_event

            profit_loss_usd_for_time_period = profit_loss_usd_per_event * number_of_funding_events_in_time_period

            return profit_loss_usd_for_time_period

        except Exception as e:
            logger.error(f'CheckProfitability - Error estimating ByBit profit for {symbol}: {e}')
            return None

    def estimate_okx_profit(self, time_period_hours: float, size_usd: float, opportunity: dict) -> float:
        try:
            symbol = opportunity['symbol'] + '-USDT-SWAP'
            is_long = opportunity['long_exchange'] == 'OKX'
            funding_rate = opportunity['long_exchange_funding_rate'] if is_long else opportunity['short_exchange_funding_rate']
            number_of_funding_events_in_time_period = self.okx_caller.get_next_funding_events_for_time_period(symbol, time_period_hours)

            if is_long:
                if funding_rate > 0:
                    # rate positive, long
                    profit_loss_usd_per_event = size_usd * funding_rate
                    profit_loss_usd_per_event = -profit_loss_usd_per_event
                else:
                    # rate negative, long
                    profit_loss_usd_per_event = size_usd * abs(funding_rate)
            else:
                if funding_rate > 0:
                    # rate positive, short
                    profit_loss_usd_per_event = size_usd * funding_rate
                else:
                    # rate negative, short
                    profit_loss_usd_per_event = size_usd * abs(funding_rate)
                    profit_loss_usd_per_event = -profit_loss_usd_per_event

            profit_loss_usd_for_time_period = profit_loss_usd_per_event * number_of_funding_events_in_time_period

            return profit_loss_usd_for_time_period

        except Exception as e:
            logger.error(f'CheckProfitability - Error estimating OKX profit for {symbol}: {e}')
            return None

    def estimate_GMX_profit(self, time_period_hours: float, absolute_size_usd: float, opportunity: dict, open_interest: dict) -> float:
        is_long: bool = opportunity['long_exchange'] == 'GMX'
        symbol = str(opportunity['symbol'])
        initial_funding_rate_8h = opportunity['long_exchange_funding_rate_8hr'] if is_long else opportunity['short_exchange_funding_rate_8hr']
        initial_funding_rate_24h = initial_funding_rate_8h * 3

        try:
            skew_usd = GMXMarketDirectory.get_skew_usd_from_open_interest(symbol, open_interest)
            new_funding_velocity_24h = GMXMarketDirectory.calculate_new_funding_velocity(
                symbol,
                absolute_size_usd,
                is_long,
                open_interest
                )
            adjusted_size_usd = get_adjusted_size(absolute_size_usd, is_long)
            skew_usd_after_trade = skew_usd + adjusted_size_usd
            opening_fee = GMXMarketDirectory.get_total_opening_fee(symbol, skew_usd, is_long, absolute_size_usd)
            closing_fee = GMXMarketDirectory.get_total_closing_fee(symbol, skew_usd_after_trade, is_long, absolute_size_usd)
            gas_fee_usd = 1
            price_impact = GMXMarketDirectory.get_price_impact_for_trade(
                opportunity,
                is_long,
                absolute_size_usd,
                self.gmx_prices
            )

            total_funding = calculate_profit_gmx(
                absolute_size_usd,
                time_period_hours,
                new_funding_velocity_24h,
                initial_funding_rate_24h
            )
            
            total_fees = (opening_fee + price_impact + gas_fee_usd + closing_fee)
            profit_after_fees = total_funding - total_fees

            return profit_after_fees

        except Exception as e:
            logger.error(f'CheckProfitability -  Error estimating GMX profit for {symbol}: Error: {e}', exc_info=True)
            return None

    def estimate_perennial_profit(self, time_period_hours: dict, absolute_size_usd: float, opportunity: dict) -> float:
        try:
            symbol = opportunity['symbol']
            is_long: bool = opportunity['long_exchange'] == 'Perennial'
            initial_funding_rate_8h = opportunity['long_exchange_funding_rate_8hr'] if is_long else opportunity['short_exchange_funding_rate_8hr']
            new_funding_rate = calculate_new_funding_velocity_perennial(
                symbol,
                absolute_size_usd,
                is_long
            )
            

        except Exception as e:
            logger.error(f'CheckProfitability -  Error estimating Perennial profit for {symbol}: Error: {e}', exc_info=True)
            return None


    def estimate_profit_for_time_period(self, hours_to_neutralize_by_exchange: dict, size_usd_per_side: float, opportunity: dict) -> dict:
        try:
            symbol = opportunity['symbol']
            long_exchange = opportunity['long_exchange']
            short_exchange = opportunity['short_exchange']
            hours_to_neutralize_long = hours_to_neutralize_by_exchange['long_exchange']
            hours_to_neutralize_short = hours_to_neutralize_by_exchange['short_exchange']
            long_exchange_funding_rate = float(opportunity['long_exchange_funding_rate_8hr'])
            long_exchange_funding_rate_1hr = long_exchange_funding_rate / 8
            short_exchange_funding_rate = float(opportunity['short_exchange_funding_rate_8hr'])
            short_exchange_funding_rate_1hr = short_exchange_funding_rate / 8
            shortest_time = float(min(hours_to_neutralize_long, hours_to_neutralize_short))


            long_profit_loss = 0
            if hours_to_neutralize_long == "No Neutralization":
                long_profit_loss = self.default_trade_size_usd * long_exchange_funding_rate_1hr * shortest_time
            else:
                long_profit_loss = self.estimate_profit_for_exchange(shortest_time, size_usd_per_side, opportunity, long_exchange)

            short_profit_loss = 0
            if hours_to_neutralize_short == "No Neutralization":
                short_profit_loss = self.default_trade_size_usd * short_exchange_funding_rate_1hr * shortest_time
            else:
                short_profit_loss = self.estimate_profit_for_exchange(shortest_time, size_usd_per_side, opportunity, short_exchange)

            total_profit_loss = long_profit_loss + short_profit_loss

            pnl_dict = {
                'symbol': symbol,
                'total_profit_loss': total_profit_loss,
                'long_exchange_profit_loss': long_profit_loss,
                'short_exchange_profit_loss': short_profit_loss
            }

            return pnl_dict

        except ValueError as ve:
            logger.error(f'CheckProfitability - Validation Error: {ve}')
            return None
        except Exception as e:
            logger.error(f'CheckProfitability - Unexpected error when estimating profit for {symbol}: {e}', exc_info=True)
            return None
