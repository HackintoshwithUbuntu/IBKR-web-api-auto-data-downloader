from decimal import Decimal
import requests
from requests.adapters import HTTPAdapter, Retry
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import csv

# Apologies for the lack of consistency in quotation style in this file

DEFAULT_API_URL = "https://localhost:5000/v1/api"
FIELDS_TO_WRITE = ["t","o","h","l","c","v"] # Debugging ["query", "vc", "vf", "tf"]
LARGE_BARS = ("m", "w", "y")
MAX_RESULTS_PER_QUERY = 1000
# Timeout for requests to api, the server already cancels at approx 10 seconds
REQUEST_TIMEOUT = 20
BAR_TO_PERIOD_MAP = {
    # Seconds
    "1S": "16min",
    "5S": "80min",
    "10S": "160min",
    "15S": "240min",
    "30S": "480min",
    # Minutes
    "1min": "16h",
    "2min": "32h",
    "3min": "48h",
    "5min": "12d",
    "10min": "24d",
    "15min": "36d",
    "20min": "48d",
    "30min": "72d",
    # Hours
    "1h": "140d",
    "2h": "35w",
    "3h": "35w",
    "4h": "35w",
    "8h": "35w",
    # Day / Week / Month
    "1d": "44m",
    "1w": "210m",
    "1m": "30y",
}

class IbkrWebDlClient:
    def __init__(self, apiUrl: str = DEFAULT_API_URL, certVerify: bool = True, debug: bool = False):
        self.apiUrl = apiUrl.rstrip("/")
        self.debug = debug
        self.certVerify = certVerify
        # Retry mechanism
        self.session = requests.Session()
        retries = Retry(
            total = 3,
            backoff_factor = 0.2,
            status_forcelist = [500, 502, 503, 504],
            raise_on_status = False
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.mount("http://", HTTPAdapter(max_retries=retries))

    # Internal GET helper with retries and error handling
    def _get(self, path: str, params: dict) -> dict:
        # TODO rate limiting could be applied here as this function is shared. 
        # Notably short bars need more strict + bid_ask counts as 2 requests
        r = self.session.get(f"{self.apiUrl}{path}", params=params, verify=self.certVerify)
        self.debugPrint(r.request.url)

        if r.status_code != 200:
            raise requests.HTTPError(r.text, response=r)
        return r.json(parse_float=str)

    def debugPrint(self, msg: str) -> None:
        if self.debug:
            print(msg)

    # Allows parsing different types of times returned by the API
    @staticmethod
    def formatTime(time):
        if type(time) is str:
            time = datetime.strptime(time, "%Y%m%d-%H:%M:%S").replace(tzinfo=timezone.utc)

        if type(time) is int:
            time = time / 1000.0
            time = datetime.fromtimestamp(time, tz=timezone.utc)

        # This is mostly a debugging tool
        if type(time) is datetime:
            if time.tzinfo is None:
                time = time.replace(tzinfo=timezone.utc)
            ny_time = time.astimezone(ZoneInfo("America/New_York"))
            fmt = "%Y-%m-%d %a %I:%M %p"
            time = f"(utc) {time.strftime(fmt)}, (NY) {ny_time.strftime(fmt)}"
            
        return time

    def queryHistoricData(
        self, 
        conid: int,
        bar: str,
        startTime: datetime = None,
        outsideRth: bool = False,
        source: str = None,
        period: str = None
    ):
        if startTime:
            startTime = startTime.strftime('%Y%m%d-%H:%M:%S')

        params = {
            'conid' : conid,
            'bar' : bar,
            'startTime' : startTime,
            'outsideRth' : outsideRth,
            'source' : source,
            'period' : period
        }
        data = self._get("/iserver/marketdata/history", params=params)
        ochlvt = data['data']
        for x in ochlvt:
            x['vf'] = data['volumeFactor']
            
        return ochlvt

    # Method to automatically download minRows rows of data for a given conid. Starting time defaults to current time if not provided.
    def getDataByConid(
        self,
        conid: int,
        bar: str,
        fileName: str,
        minRows: int,
        startTime: datetime = None,
        outsideRth: bool = False,
        source: str = None,
        period: str = None
    ):
        if bar not in BAR_TO_PERIOD_MAP.keys():
            self.debugPrint(f"Selected bar is invalid, valid bars are: {list(BAR_TO_PERIOD_MAP.keys())}")
        
        curRows = 0
        queryNum = 0
        curTime = startTime
        period = period or BAR_TO_PERIOD_MAP[bar]
        fileIsEmpty = not os.path.exists(fileName) or os.path.getsize(fileName) == 0

        with open(fileName, 'a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS_TO_WRITE, extrasaction="ignore")
            if fileIsEmpty:
                writer.writeheader()

            while curRows < minRows:
                data = self.queryHistoricData(
                    conid = conid,
                    bar = bar,
                    startTime = curTime,
                    outsideRth = outsideRth,
                    source = source,
                    period = period
                )
                # Note first = earliest, last = latest
        
                # More than 1000 results returned, a smaller period is required
                if len(data) >= MAX_RESULTS_PER_QUERY:
                    self.debugPrint(f"More than {MAX_RESULTS_PER_QUERY} results returned, setting a smaller period override is recommended (but not required if you encouter no timeouts). Period currently used was {period}")

                # The earliest and latest bars can be partial bars, we exclude them to ensure we only deal with full bars
                if bar.endswith(LARGE_BARS):
                    lastBarToKeep = -1 if queryNum else None
                    data = data[1:lastBarToKeep]

                curRows += len(data)
                queryNum += 1
                # Since we can't trust the earliest bar in this dataset and the coverage of the latest bar in the next query is inconsistent, this is the safest option
                if len(data) < 3: 
                    self.debugPrint("Reached end of available data")
                    break
                curTime = datetime.fromtimestamp(data[1]['t']/1000.0, tz=timezone.utc)
                self.debugPrint(curTime)

                for item in data:
                    item['v'] = int(Decimal(item['v']) * item['vf'])
                    # Debug purposes
                    item['tf'] = self.formatTime(item['t'])
                    item['query'] = queryNum

                data.reverse()
                # TODO limit this to only write minRows if we are going over
                writer.writerows(data)

    def queryStockConid(self, ticker: str) -> int:    
        params = {
            'symbols' : ticker
        }
        data = self._get("/trsrv/stocks", params=params)
        return data

    # Resolve a stock ticker to a conid
    def getConidFromStock(self, ticker: str) -> int:
            # TODO this is far from perfect but good enough to get going, users should be able to specify filtering applied
            for key, stock in self.queryStockConid(ticker).items():
                for security in stock:
                    for contract in security['contracts']:
                        if contract['isUS']:
                            return contract['conid']
    
            raise ValueError(f'No US stocks found for query "{ticker}", use conid for non-US stocks')


    # Method to download data for stocks using their ticker. Currently defaults to US stocks. Use the getDataByConid for non-US stocks
    def getDataByStock(
        self,
        ticker: str,
        bar: str,
        fileName: str,
        minRows: int,
        startTime: datetime = None,
        outsideRth: bool = False,
        source: str = None,
        period: str = None
    ):
        conid = self.getConidFromStock(ticker)
        self.getDataByConid(
            conid = conid,
            bar = bar,
            fileName = fileName,
            minRows = minRows,
            startTime = startTime,
            outsideRth = outsideRth,
            source = source,
            period = period
        )

    def queryConid(self, symbol: str):
        if "," in symbol:
            raise ValueError("Only one symbol can be searched for")
        params = {
            'symbol' : symbol
        }
        data = self._get("/iserver/secdef/search", params=params)
        return data

    # Resolve a symbol to a conid
    def getConidFromSymbol(self, symbol: str):
        # TODO again, better filtering mechanism would be preferable so can select things like CFDs
        for item in self.queryConid(symbol):
            return item['conid']

        raise ValueError(f'No instrument found for query "{symbol}". queryConid() can help you test why this error appears')

    # Method to download data for securities that aren't stocks
    def getDataBySymbol(
        self,
        symbol: str,
        bar: str,
        fileName: str,
        minRows: int,
        startTime: datetime = None,
        outsideRth: bool = False,
        source: str = None,
        period: str = None
    ):
        # TODO Lot of duplication with the stock method, might bring these together in future
        conid = self.getConidFromSymbol(symbol)
        self.getDataByConid(
            conid = conid,
            bar = bar,
            fileName = fileName,
            minRows = minRows,
            startTime = startTime,
            outsideRth = outsideRth,
            source = source, 
            period = period
        )