import yfinance as yf
import sqlite3
import sys

def stock_price_pull(stock_names = ['SPY', 'IEF'], 
                     time_period = '1y', 
                     time_interval = '1d',
                     measure = 'Close',
                     database = 'stocks.db'):

    stock_names_string_space = " ".join(stock_names)

    stock_names_string_underscore = "_".join(stock_names)

    stocks_raw = yf.download(tickers = stock_names_string_space,
                             period = time_period,
                             interval = time_interval)
    
    stocks_clean = stocks_raw[measure].sort_values(by = 'Date', 
                                           ascending = False)
    
    con = sqlite3.connect(database)

    table_name = f'{stock_names_string_underscore.lower()}_{measure.lower()}'

    stocks_clean.to_sql(table_name, con, if_exists='replace')

    print(f'Stock price pull complete. The table is stored in the {database} database in the {table_name} table.')

if __name__ == "__main__":
    stock_price_pull()
