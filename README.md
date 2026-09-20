# IBKR Auto Web API Data Downloader
A Python client to allow easy download of bulk historical data from the IBKR Web API for stocks, forex, crypto and other securities. 

Get historic data for a variety of securities without having to sign up for a different data provider. 

```sh
pip install ibkrautowebdl
```

Why the Web API (over TWS)?
- Lighter on pc
- Less dependencies and easier setup 
- Easier to use than async library
- Can even be used without installing any programs with oauth

Library Features
- Simple setup
- CSV exports
- Data saved directly to disk so not lost on crash (and lower memory usage)
- Minimal dependencies (only requires `requests` library)
- No precision loss for any decimal values returned via API
- Broad asset support including stocks, forex, crypto and more

Upcoming features
- Handling for lower rate limits for bars smaller than 30 seconds
- Specify a date to download until
- Numbering of documentation items so they can easily be cross-referenced with notebook
- More extensible filtering mechanism to allow more easily selecting non-US securities without knowing a conid in advance
- Auto rate-limiting (Not really needed given speed of single threading unless going for bars of 30 secs or less)

Goals (longer-term)
- Multithreading
  - Difficult due to unpredictability of API as outlined below
- Ibind support for oauth
- Resume from left off on failure
- Command line tool
- In-memory downloads and Pandas integration
- Dynamic resizing of period window based on number of results returned

## Getting Started

Download the [Client Portal Gateway](https://www.interactivebrokers.com/docs/web-api/api/web-api/quick-start) (and ensure Java is installed)

To start the gateway, navigate into the `clientportal.gw` folder and run 
```powershell
bin\run.bat root\conf.yaml
```
or if you are on *Nix / MacOS
```sh
bin/run.sh root/conf.yaml
```
and then login (a Paper account will work fine for data downloads). 

### Example
You can then use the library as following, run like you would with any other Python file to download the CSVs (you may want to use a tool such as `screen` or `tmux` if starting a long-running download)
```py
from ibkrautowebdl import IbkrWebDlClient
from datetime import datetime
import urllib3
# Suppress warnings from CP Gateway self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# We also need to skip TLS verification for the CP Gateway certificate
# This is fine when using the Gateway locally (majority of cases) but be careful if you ever host it on a different machine
client = IbkrWebDlClient(certVerify=False)
# How to set a custom server
# client = IbkrWebDlClient("https://localhost:6000/v1/api", certVerify=False, debug=True)

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
```

While at a surface level the code of this library looks quite simple. It took extensive experimentation with the IBKR API to produce a client that could consitently download data for a variety of different instruments. The majority of this effort was spent in attempting to demystify some of the inconsistent behaviours of the IBKR API. To help those in future, I have documented my efforts so others can benefit. 

## The IBKR Web API and its idiosyncrasies

The IBKR API does a number of weird and wonderful things. I hope that my experiences, experimentations and results can save you much frustration. 

At the time of writing, the IBKR web API docs have recently undergone an update. Previously the only extra limit on requests for historical data from the `/iserver/marketdata/history` endpoint was that a maximum of 5 requests were issued concurrently, this has recently [September 9 2026](https://www.interactivebrokers.com/docs/web-api/changelog/2026/9/9) been updated to be further limited to only 10 req/s or 50 req/minute. The restriction on requests per minute is particularly restricting compared to the more generous previous limits (and those offered by TWS)

For the purposes of this guide, we will consider any bars of size under 1 week as "Small bars", while "large bars" will be those those of size 1 week and over. 

Each of the points below is supplemented by examples in the file [`dataShow.ipynb`](./dataShow.ipynb)

### Small Bar Sizes

The Web API documentation for historical data seems to have a table where the minimum period and bar is only 1 minute. However, the API does in fact seem to accept smaller bar sizes. Unusually however, while the API does respond, the returned bars seem to be 1 minute apart, as a consequence the given `period` value is not followed but the number of returned bars does seem to conform to $\frac{\text{bar}}{\text{period}}$.

The API definitely still seems to recognise valid [TWS bar sizes](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-bars/historical-bar-sizes) which we can see by the fallback to returning 10 minutes of data when an invalid bar size is inputted.

What is more unusual is that despite the returned timings all being one minute apart, when comparing multiple such queries with bars in seconds to their minutes equivalents, the opening and closing values rarely match across multiple queries. However, between each bar, the opening and closing prices do (roughly) match which seems to imply that the bars are continuous despite what the returned time says. This is backed up by the fact that when comparing opening and close between a 15s bar and a 1min bar then we get matches of open and close every 4 bars. As such, the most likely conclusion is that smaller bars do in fact work, however the times returned by the api are incorrect.

While this is the case at the time of writing, there may be further updates to the API in future that fix this issue. If I recall correctly, this was not an issue when I first started using the API. 

### Fetching too many bars

Making a request that returns more than 1000 bars doesn't result in an error being returned automatically. Clipped data will still be returned if the request can be served within 10 seconds of IBKR server processing time. If you submit such a request that it takes more than 10 seconds to process, then your request is cancelled and you are returned an error. 

### Different timezones returned and large bar differences

Communication with the IBKR Web API is all done in the UTC timezone. However, the timestamps returned with OCHLV data have some dynamic behaviours. 

For bars of size 1 day or smaller, the returned epoch time will be at the start of the trading day (or trading hours in case `outside_rth` is enabled). However, for larger bars (1 week or more), then the returned epoch time corresponds to 12:00AM UTC at the start of the bar's period. So for weekly bars, this is set to 12:00 AM UTC on Monday (in UTC) to indicate which week this bar corresponds to. Despite this result being returned in UTC as opposed to the local market timing, All results are still aggregated correctly as if the bar started at 12:00 AM on the same date in the trading time zone. 

Furthermore, the returned epoch time for larger bars will skip any weekends or non-trading days if they are the first day of the period (For example Jan 2nd being the anchor for January since no trading on Jan 1).

### Partial bars and bar snapping for large bars

While larger bars will usually snap to the start of the relevant period (monthly bars will start from first trading day of month), the earliest bar returned will often be a "partial" bar. Instead of returning data for the whole month, the earlier bar will snap onto some other date and then return statistics from the remaining part of the period after the starting date the server selected. For example, when requesting monthly bars, all of the bars will start on the 1st trading day of the month, however the first/earliest bar returned may start on the 10th trading day of the month. This often makes the earliest bar returned unreliable to use for data. 

These partial bars are unrelated to the start date provided. Say the date given to the API is the 20th day of the month, the earliest bar returned may be on the 10th (as opposed to starting on the 20th). Furthermore, the server seems to have dates that it likes to snap to when returning data since adjusting your selected date to fetch data from by plus/minus a few days will usually result in the exact same partial bar being returned. There doesn't seem to be a strong pattern in the dates that the server chooses to snap to. 

It can also happen that the date on the bar is correct, however the data returned with the date doesn't reflect the movements of the underlying security over the whole bar period. 

Furthermore, sometimes the number of bars (when including the partial bar) is inconsistent. When requesting 16 months of monthly data you may be returned with 17 bars, however when requesting 17 months of monthly data from the same date, you may again get 17 bars, this time with the earliest (partial) bar upgraded to a full bar. This can even happen when you ask for monthly bars for a period of 1 month and get 2 results! 

### Inclusion of provided date for large bars

The behaviour for whether the final bar includes the actual date passed to the API is again inconsistent. For exmaple: when requesting monthly bars from 21st Feb, the server may choose to provide bars up to and including January, however, when requesting those same bars from 22nd Feb then the server may choose to include the February bar as well. The boundary for whether the current month (or other larger bar) will be included in the current query seems to vary from month to month. As such, you cannot assume that the final bar returned by the API will actually cover the date you provide.  

For small bars, the last bar is always not included, for example a start time of 3pm with 1 min bars would have the final bar starting at 2:58pm (and have no 2:59pm bar).

