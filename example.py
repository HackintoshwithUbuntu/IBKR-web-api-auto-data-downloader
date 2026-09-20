from ibkrautowebdl import IbkrWebDlClient
from datetime import datetime
import urllib3
# Suppress warnings from CP Gateway self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# We also need to skip TLS verification for the CP Gateway certificate
# This is fine when using the Gateway locally (majority of cases) but be careful if you ever host it on a different machine
client = IbkrWebDlClient(certVerify=False)
# How to set a custom server
# client = IbkrWebDlClient("https://localhost:6000/v1/api", certVerify=False)

# Fetches at least 5000 1h bars for AAPL stock, starting from the current time, saved to data.csv
client.getDataByStock("AAPL", "1h", "data.csv", 5000)

# Saves at least 1000 1d AUD.USD bars to forex.csv, starting from current time
client.getDataBySymbol(symbol="AUD.USD", bar="1d", fileName="forex.csv", minRows=1000)

# Example with most fields filled
# Saves at least 10,000 10min BTC bars to crypto.csv
# Uses midpoint (of bid-ask) starting from 14 Sept 2026 3:00pm UTC and includes trading outside regular trading hours
client.getDataBySymbol(
    symbol="BTC", 
    bar="10min", 
    fileName="crypto.csv", 
    minRows=10000, 
    startTime=datetime(2026, 9, 14, 15, 0),
    outsideRth=True, # Doesn't affect crypto
    source="Midpoint", # One of Last, Midpoint or Bid_Ask (default Last)
    # period="160h" # Controls how many rows returned per query, may be useful to adjust if you encouter timeouts
)

# For niche securities you may prefer to use the conid directly
# print(client.queryConid("BRK"))
# client.getDataByConid(198013455,"1h", "data.csv", 5000)