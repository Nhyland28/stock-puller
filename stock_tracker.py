import yfinance as yf
import sqlite3
from datetime import date
import pandas as pd
import time

def closing_price_pull(stock_list_name = 'sp500',
                       start_date = '2018-01-01',
                       database = 'stocks.db',
                       time_interval = '1d'):
    '''
    First, the function reads the csv file passed in stock_list name to determine what stocks are wanted. The function then pulls adjusted closing price data from YFinance, transforms the returned table into a long format (date, ticker, 
    adjusted closing price), and then saves the table to a SQL table. This function needs to be run before the share_pull 
    function. 
    '''
    
    stock_list_df = pd.read_csv(f'{stock_list_name}.csv')
    stock_list_df['Symbol Clean'] = stock_list_df['Symbol'].replace('/','-')
    stock_list = list(stock_list_df['Symbol Clean'])

    stocks_close_long = pd.DataFrame(columns=['Date', 'Ticker', 'Closing_Price'])

    step = 250

    for i in range(0, len(stock_list), step):
        x = i
        mini_list = stock_list[x:x+step]

        mini_list = " ".join(mini_list)
        stocks_raw = yf.download(tickers = mini_list,
                                start = start_date,
                                interval = time_interval)
        
        stocks_close = stocks_raw.loc[:, ['Adj Close']]
        stocks_close.columns = stocks_close.columns.droplevel()
        stocks_close['Date'] = stocks_close.index
        stocks_close.reset_index(drop = True, inplace = True)
        
        stocks_close_long_temp = pd.melt(stocks_close, id_vars=['Date'], var_name='Ticker', value_name='Closing_Price')

        stocks_close_long = pd.concat([stocks_close_long, stocks_close_long_temp])

        print(f'Finished section: {x} ---> {x+step}')
        time.sleep(3)

    con = sqlite3.connect(database)

    table_name = f'{stock_list_name}_closing_price'

    stock_list_df_filtered = stock_list_df[['Symbol Clean', 'Section']]
    stocks_close_long = stocks_close_long.merge(stock_list_df_filtered, how='left', left_on='Ticker', right_on='Symbol Clean')
    stocks_close_long.drop(columns='Symbol Clean', inplace=True)

    stocks_close_long.to_sql(table_name, con, if_exists='replace')

    print(f'Stock price pull complete. The table is stored in the {database} database in the {table_name} table.')



def share_pull(stock_list_name = 'sp500',
               start_date = '2018-01-01',
               section = 1,
               database = 'stocks.db'):    
    '''
    First, the function reads the csv file passed in stock_list name to determine what stocks are wanted. It then loops through the csv
    subset determined by the section argument (e.g. if section = 1 then it loops through the first subset). Within each subset the function
    pulls the outstanding share amount from YFinance, transforms it to a long table, downloads the same table from the SQL database and
    then updates it with new data. It then pulls the closing price data, merges it, multiplies the closing price and outstanding shares
    to get the market cap, and then saves that to the database.
    '''
    
    # Establish a connection with the database
    con = sqlite3.connect(database)

    # Read the stock list csv
    stock_list = pd.read_csv(f'{stock_list_name}.csv')

    # Creates an empty dataframe with a date column
    ## Date column is at a daily interval going back to the selected start date
    generic_date_range = pd.date_range(start = pd.Timestamp(start_date),              
                                   end = pd.to_datetime(date.today()),
                                   freq = 'D')
    
    # Transform the timestamp column into a date column
    share_df = pd.DataFrame(generic_date_range, columns = ['Date'])
    share_df['Date'] = share_df['Date'].dt.date
    
    # Pulls the corresponding section table from the database to a dataframe
    table_name = f'{stock_list_name}_{section}_shares'
    section_table = pd.read_sql_query(f"SELECT * FROM {table_name}", con)
    section_table = section_table.drop(columns=['index'])

    # Filters the stock list csv to only show data on the specified section
    filtered_shares_list = stock_list[stock_list['Section'] == section]
    
    # Loops through each share in the filtered section stock list
    for index, row in filtered_shares_list.iterrows():
        try:

            # Find the latest date in section table for the specified ticker
            share = row['Symbol']
            section_table_stock = section_table[section_table['Ticker'] == share]

            # Pull share data from API
            tic = time.perf_counter()

            ticker = yf.Ticker(share.upper())

            # Transform the returned dataframe to a cleaner table
            individual_share = ticker.get_shares_full(start = start_date, end = None)
            individual_share_df = individual_share.to_frame()
            individual_share_df = individual_share_df.rename(columns = {0:f'{share.upper()}'})
            individual_share_df['Date'] = individual_share_df.index
            individual_share_df['Date'] = individual_share_df['Date'].dt.date
            individual_share_df = individual_share_df.reset_index(drop=True)
            individual_share_df = individual_share_df.drop(individual_share_df.tail(1).index)

            # Merge the share information for the one specific stock into a table with all the shares
            share_df = share_df.merge(individual_share_df, on = 'Date', how = 'left')   
            # Fill an missing values with the preceding value 
            share_df = share_df.fillna(method='ffill') 

            # Store the last date stored
            last_date = share_df['Date'].tail(1)

            toc = time.perf_counter()
            time_spent = toc - tic

            print(f'{share}: Done downloading - {time_spent:0.4f} seconds')
        
        except:
            print('Error getting stock information for one of the stocks.')

    # Remove any duplicate dates by grouping by Date and taking the first observation
    share_df = share_df.groupby('Date').nth(0)
    share_df['Date'] = share_df.index
    share_df.reset_index(drop=True, inplace=True)
    
    # Make the table long instead of wide (e.g. each stock was it's own column)
    share_df_long = pd.melt(share_df, id_vars=['Date'], var_name='Ticker', value_name='Outstanding_Shares')

    # Convert the open shares to numeric
    share_df_long['Outstanding_Shares'] = pd.to_numeric(share_df_long['Outstanding_Shares'], errors='coerce')

    # Specify the interval
    share_df_long['Section'] = section

    # Set the table name which is just the name of the stock list, section, and 'shares'
    table_name = f'{stock_list_name}_{section}_shares'

    # Pull the old share dataframe from the database
    old_share_df_long = pd.read_sql_query(f"SELECT * FROM {table_name}", con)

    # Add the new data
    new_share_df_long = pd.concat([share_df_long, old_share_df_long])

    # Remove the index
    new_share_df_long.drop(columns='index', inplace=True)

    # Save the new share table to the database (has the updated data)
    new_share_df_long.to_sql(table_name, con, if_exists='replace')

    # Get the name of the closing price table
    closing_price_table_name = f'{stock_list_name}_closing_price'

    # Pull all the data and save it to a dataframe
    closing_price_table = pd.read_sql_query(f"SELECT * FROM {closing_price_table_name}", con)

    # Drop the index (creates one by default)
    closing_price_table.drop(columns='index', inplace=True)

    # Ensure the date is formatted correctly
    closing_price_table['Date'] = pd.to_datetime(closing_price_table['Date']).dt.date

    # Load in old merged table from SQL database
    old_merge_table = pd.read_sql_query(f"SELECT * FROM {stock_list_name}", con)

    # Drop the index (from the old table)
    old_merge_table.drop(columns='index', inplace=True)

    # Ensure the date is formatted correctly
    old_merge_table['Date'] = pd.to_datetime(old_merge_table['Date']).dt.date

    # Drop data from the old_merge_table that was previously in there for the specified interval
    interval_index = old_merge_table[old_merge_table['Section'] == section].index
    old_merge_table.drop(interval_index, inplace=True)

    # Merge the closing price data and share price data
    partial_merge_table = pd.merge(closing_price_table, new_share_df_long, how = 'inner', on = ['Date', 'Ticker', 'Section'])

    # Create a new variable called 'Market Cap' which multiplies the closing price by open shares
    partial_merge_table['Market_Cap'] = partial_merge_table['Closing_Price'] * partial_merge_table['Outstanding_Shares']

    final_merge_table = pd.concat([old_merge_table, partial_merge_table])

    # Save that table to the SQL database
    final_merge_table.to_sql(stock_list_name, con, if_exists='replace')

def initialize_tables(stock_list_name = 'sp500',
                      start_date = '2017-12-31'):
    '''
    This function initiliazes a new data model for the database. Each time there is a new csv file (list of stocks) you must run this function.
    It will create the empty share tables based on the section. If you have 10 distinct sections then it will create 10 different sahre tables.
    '''
    
    stock_list = pd.read_csv(f'{stock_list_name}.csv')

    interval = stock_list['Section'].max()

    for i in range(1, interval+1):
        stock_list_partitioned = stock_list[stock_list['Section'] == i]
        stocks = list(stock_list_partitioned['Symbol'])
        
        db_table = pd.DataFrame(columns=['Date', 'Ticker', 'Outstanding_Shares', 'Section'])
        db_table['Ticker'] = stocks
        db_table['Date'] = start_date
        db_table['Outstanding_Shares'] = 'NA'

        con = sqlite3.connect('stocks.db')

        table_name = f'{stock_list_name}_{i}_shares'

        db_table.to_sql(table_name, con, if_exists='replace')

    table_name_merged = f'{stock_list_name}'

    db_table_merged = pd.DataFrame(columns=['Date', 'Ticker', 'Closing_Price', 'Outstanding_Shares', 'Market_Cap', 'Section'])

    db_table_merged.to_sql(table_name_merged, con, if_exists='replace')


    


if __name__ == "__main__":
    print('What are you trying to do: \n [1] Initialize a new project \n [2] Update closing price date \n [3] Update share date')    
    program_type = input()
    if program_type == '1':
        print('What stock list are you trying to start a project with? This is the name of the .csv file that holds the stock names. Do not include the ".csv" portion of the file name (e.g. "sp500.csv" should be entered as "sp500"). The default value is the S&P 500')
        stock_list_name = input()
        initialize_tables(stock_list_name=stock_list_name)
    elif program_type == '2':
        print('What stock list are you trying to update the closing prices with? This is the name of the .csv file that holds the stock names. Do not include the ".csv" portion of the file name (e.g. "sp500.csv" should be entered as "sp500"). The default value is the S&P 500')
        stock_list_name = input()
        closing_price_pull(stock_list_name=stock_list_name)
    elif program_type == '3':
        print('What stock list are you trying to update the open shares with? This is the name of the .csv file that holds the stock names. Do not include the ".csv" portion of the file name (e.g. "sp500.csv" should be entered as "sp500"). The default value is the S&P 500')
        stock_list_name = input()
        print('What interval (e.g. 1, 2, or 3)')
        interval = input()
        interval = int(interval)
        share_pull(stock_list_name=stock_list_name, section=interval)

    else:
        print('Please enter either a 1, 2, or 3 to select a program. \n [1] Initialize a new project \n [2] Update closing price date \n [3] Update share date')