# AI Stock Trading: External Services & APIs (With Costs)

## 1. STOCK MARKET DATA PROVIDERS

### Real-Time Market Data (Required)

#### **Alpha Vantage**
- **Cost:** $0-500/month (free to paid tiers)
- **What it provides:** Real-time stock prices, historical data, technical indicators
- **API calls:** Free = 5 calls/min, Paid = 500+ calls/min
- **Best for:** Basic data needs, starting point
- **Website:** https://www.alphavantage.co
- **Pros:** Easy to use, affordable, good documentation
- **Cons:** Rate limits, slower than premium alternatives

#### **IEX Cloud**
- **Cost:** $100-1,000+/month
- **What it provides:** Real-time quotes, historical data, company data, news
- **Latency:** Sub-second updates
- **Best for:** Small to medium trading volume
- **Website:** https://iexcloud.io
- **Pros:** Fast, reliable, good documentation
- **Cons:** More expensive than Alpha Vantage

#### **Polygon.io**
- **Cost:** Free-$600+/month
- **What it provides:** Stock, crypto, forex data; real-time prices; historical bars
- **API calls:** Free tier has limits, paid tiers offer unlimited
- **Best for:** Multi-asset (stocks + crypto)
- **Website:** https://polygon.io
- **Pros:** Excellent data quality, institutional-grade
- **Cons:** Pricing can get expensive for high volume

#### **Finnhub**
- **Cost:** Free-$500/month
- **What it provides:** Real-time data, company news, earnings calendar, economic data
- **Best for:** Combining prices with news/fundamentals
- **Website:** https://finnhub.io
- **Pros:** Great news integration, good free tier
- **Cons:** Rate limits on free tier

#### **Interactive Brokers Data**
- **Cost:** Free (if trading through them) or $150-500/month standalone
- **What it provides:** Real-time market data, depth of book, options data
- **Best for:** If you're trading through IB anyway
- **Website:** https://www.interactivebrokers.com
- **Pros:** Highest quality data, most comprehensive
- **Cons:** Expensive if you're not trading through them

---

## 2. NEWS & SENTIMENT DATA PROVIDERS

### Financial News APIs (Important for correlation analysis)

#### **NewsAPI (Financial)**
- **Cost:** $150-450/month
- **What it provides:** Financial news from 30,000+ sources
- **Update frequency:** Real-time
- **Best for:** Broad market news sentiment
- **Website:** https://newsapi.org
- **Pros:** Large source coverage, affordable
- **Cons:** Requires sentiment analysis on your end

#### **Finnhub News API**
- **Cost:** Free-$500/month (included in their platform)
- **What it provides:** Company news, earnings calendars, economic events
- **Best for:** Company-specific sentiment
- **Website:** https://finnhub.io
- **Pros:** Good integration with other Finnhub data
- **Cons:** Limited free tier

#### **MarketWatch/Seeking Alpha APIs**
- **Cost:** $100-500/month (various scraping services)
- **What it provides:** News, analyst ratings, earnings surprises
- **Best for:** Expert sentiment and ratings
- **Pros:** Professional analysis included
- **Cons:** High cost, TOS restrictions on some

#### **Bloomberg Terminal Alternative: Benzinga API**
- **Cost:** $300-2,000+/month
- **What it provides:** Real-time news feeds, earnings alerts, market data
- **Best for:** Professional traders wanting institutional-quality data
- **Website:** https://www.benzinga.com/api
- **Pros:** Very comprehensive, professional-grade
- **Cons:** Expensive

#### **SEC Edgar API (Free)**
- **Cost:** Free
- **What it provides:** Corporate filings (10-K, 8-K, earnings reports)
- **Best for:** Fundamental analysis and earnings correlation
- **Website:** https://www.sec.gov/edgar/sec-api-documentation

---

## 3. BROKER APIs FOR TRADING EXECUTION

### Retail Brokers with API Access

#### **Interactive Brokers**
- **Cost:** $0-10/month (no monthly fee, per-trade commissions)
- **Trade commissions:** $0.01 per share (stocks), $1-3 per contract (options)
- **Minimum account:** $2,000 (regular account)
- **API:** Yes, IBKR API (IBPy)
- **Paper trading:** Yes (free, unlimited)
- **Best for:** Advanced traders, algo trading, multi-asset
- **Website:** https://www.interactivebrokers.com
- **Pros:** 
  - Lowest commissions
  - Excellent API documentation
  - Paper trading available
  - Supports all order types
- **Cons:** 
  - Steeper learning curve
  - Minimum account size

#### **Alpaca**
- **Cost:** Free (no commissions, no monthly fee)
- **Account minimum:** $0 (can start with any amount)
- **API:** Excellent REST and WebSocket API
- **Paper trading:** Yes (unlimited, highly recommended)
- **Best for:** Algo traders, starting out, paper trading
- **Website:** https://alpaca.markets
- **Pros:**
  - Completely free
  - Amazing API (designed for algo trading)
  - Paper trading environment is production-ready
  - Day trading without PDT rules (paper account)
  - Great documentation
- **Cons:**
  - Live account size limits for day traders (PDT rule: $25k minimum)
  - US equities only

#### **Robinhood**
- **Cost:** Free (no commissions)
- **Account minimum:** $0
- **API:** Very limited API (mostly unofficial/unofficial)
- **Paper trading:** No official paper trading
- **Best for:** Casual trading only, NOT recommended for algo
- **Cons:** 
  - No official API for algorithmic trading
  - Would need to use unofficial libraries
  - Not suitable for production trading

#### **TD Ameritrade (thinkorswim)**
- **Cost:** Free (no commissions)
- **Account minimum:** $0 (for some account types)
- **API:** Yes (thinkorswim API, ThinkPad)
- **Paper trading:** Yes
- **Best for:** Intermediate traders
- **Pros:** Good API, paper trading available
- **Cons:** Complex API, less ideal for algo than Alpaca/IB

#### **E*TRADE**
- **Cost:** Free (no commissions)
- **Account minimum:** $0
- **API:** Yes (REST API available)
- **Paper trading:** Limited
- **Best for:** Moderate automation
- **Pros:** Established broker, good data
- **Cons:** API less developed than others

#### **Webull**
- **Cost:** Free (no commissions)
- **Account minimum:** $0
- **API:** No official API
- **Best for:** Manual trading only, NOT for algo
- **Cons:** No API access

---

## 4. CLOUD INFRASTRUCTURE (Optional but likely needed)

If you want your trading system running 24/7:

#### **AWS (Amazon Web Services)**
- **Cost:** $50-500+/month (depending on usage)
- **Components needed:**
  - EC2 (compute): $10-50/month for small instance
  - RDS (database): $15-50/month
  - DynamoDB (no-SQL): $20-100/month
  - Data transfer: $0-50/month
- **Best for:** Enterprise-grade, scaling

#### **DigitalOcean**
- **Cost:** $6-40+/month
- **Components:**
  - Droplet (server): $4-20/month
  - Managed database: $12-30/month
- **Best for:** Simpler, cheaper alternative to AWS
- **Pros:** Affordable, easy to use
- **Website:** https://www.digitalocean.com

#### **Google Cloud Platform (GCP)**
- **Cost:** $50-500+/month
- **Similar to AWS, enterprise-grade**

#### **Heroku**
- **Cost:** $25-500+/month
- **Best for:** Quick deployment, less control
- **Pros:** Very easy to deploy
- **Cons:** More expensive than alternatives

---

## 5. SENTIMENT ANALYSIS & AI SERVICES (Optional)

If you don't want to train your own ML models:

#### **Aylien News API**
- **Cost:** $300-2,000+/month
- **What it provides:** News with pre-computed sentiment scores
- **Best for:** Outsourcing sentiment analysis
- **Website:** https://aylien.com

#### **OpenAI API (GPT)**
- **Cost:** $0.002-0.20 per 1K tokens
- **Estimate:** $50-200/month for continuous sentiment analysis
- **What it provides:** Can use GPT to analyze news sentiment
- **Best for:** Custom sentiment analysis on top of news
- **Website:** https://openai.com/api
- **Note:** Technically, you'll use AI to create your software, so you might use this as a service layer

#### **AWS Comprehend**
- **Cost:** $0.01 per 100 units (1 unit = 1 text request)
- **Estimate:** $100-500/month for high-volume sentiment analysis
- **What it provides:** Sentiment analysis, entity detection
- **Best for:** Large-scale text processing

---

## 6. MONITORING & ALERTING (Optional)

#### **PagerDuty**
- **Cost:** $10-50/month per user
- **What it provides:** Alerts, incident management
- **Best for:** Getting notified if trading system fails

#### **Slack** (for alerts)
- **Cost:** Free-$12.50/user/month
- **What it provides:** Notifications to Slack channels
- **Best for:** Real-time system alerts

#### **Datadog**
- **Cost:** $50-500+/month
- **What it provides:** Monitoring, logging, APM
- **Best for:** Professional monitoring infrastructure

---

## MINIMUM VIABLE SETUP (Budget-Conscious)

**Total monthly cost: ~$150-400/month**

### Recommended combination for starting:

1. **Stock Data:** Alpaca (free) OR Finnhub ($50/month) OR Alpha Vantage ($50-100/month)
2. **News/Sentiment:** Finnhub ($50/month includes news) OR NewsAPI ($150/month)
3. **Trading Broker:** Alpaca (free) for paper trading first
4. **Infrastructure:** DigitalOcean ($6-10/month) for running your trading bot
5. **Cloud Database:** Included with DigitalOcean or use free tier PostgreSQL

**Total: $150-300/month to start**

---

## PROFESSIONAL SETUP (Full-Featured)

**Total monthly cost: ~$1,000-3,000/month**

1. **Stock Data:** Polygon.io ($300/month) + IEX Cloud ($200/month)
2. **News/Sentiment:** Benzinga ($500/month) or Bloomberg Terminal ($2,000+)
3. **Trading Broker:** Interactive Brokers (commission-based)
4. **Infrastructure:** AWS ($200/month)
5. **Monitoring:** Datadog ($200/month)
6. **Sentiment AI:** OpenAI API ($200/month)
7. **Alerting:** PagerDuty ($50/month)

**Total: $1,500-3,000+/month**

---

## RECOMMENDED STACK FOR YOUR SETUP

### Stage 1: Paper Trading (Testing, $100-150/month)
```
Alpaca API (FREE)
├─ Real-time stock data (free with account)
├─ Paper trading account
└─ WebSocket data feed

+ Finnhub API ($50/month)
├─ Financial news
├─ Company sentiment
└─ Economic calendar

+ DigitalOcean ($6/month)
└─ Run your trading bot 24/7

Total: ~$56-100/month
```

### Stage 2: Live Trading - Small Account ($150-250/month)
```
Same as Stage 1, add:

+ NewsAPI ($150/month - optional)
└─ More comprehensive news sources

Total: ~$156-250/month
```

### Stage 3: Live Trading - Professional ($500-800/month)
```
Polygon.io ($300/month)
├─ Institutional-quality data
├─ Historical data
└─ Real-time updates

+ Finnhub ($50/month)
├─ News feeds
└─ Sentiment data

+ Interactive Brokers ($50-100 commission on trades)
├─ Better execution
└─ Options trading if needed

+ AWS or DigitalOcean ($100/month)
└─ Robust infrastructure

Total: ~$500-800/month + trading commissions
```

---

## API INTEGRATION FLOW

```
Your AI-Built Software
        ↓
┌───────┴───────┐
│               │
Data APIs    Trading API
│               │
├─ Alpaca      └─ Interactive Brokers
├─ Polygon     └─ Alpaca
├─ Finnhub
├─ NewsAPI
└─ Alpha Vantage

↓ (processed by your system)

Trading Decisions
↓
Place Orders
↓
Execute & Monitor
```

---

## PAYMENT MODELS OVERVIEW

| Service | Model | Best For |
|---------|-------|----------|
| **Alpaca** | Free | Starting out, paper trading |
| **Alpha Vantage** | Tiered ($0-500) | Budget conscious |
| **Finnhub** | Tiered ($0-500) | Balanced data + news |
| **IEX Cloud** | Tiered ($100+) | Professional needs |
| **Polygon.io** | Tiered ($0-600) | Multi-asset coverage |
| **Interactive Brokers** | Per-trade ($0.01+) | High volume trading |
| **NewsAPI** | Tiered ($150+) | Comprehensive news |
| **Benzinga** | Enterprise ($300+) | Institutional grade |
| **AWS** | Pay-as-you-go | Scaling infrastructure |
| **DigitalOcean** | Monthly flat | Budget servers |

---

## KEY DECISION: WHERE TO START

### Option A: Completely Free (Paper Trading)
- **Alpaca** for data + trading
- **Cost:** $0
- **Limitation:** Paper trading only, no real money
- **Best if:** You want to test everything first

### Option B: Affordable (Paper + Live)
- **Alpaca** for trading (free)
- **Finnhub** for data + news ($50/month)
- **DigitalOcean** for running bot ($6/month)
- **Cost:** ~$56/month
- **Great for:** Testing with small real account

### Option C: Professional
- **Interactive Brokers** for trading (pay per trade)
- **Polygon.io** for data ($300/month)
- **Finnhub** for news ($50/month)
- **AWS** for infrastructure ($200/month)
- **Cost:** ~$550+/month + trade commissions
- **Great for:** Serious traders with larger accounts

---

## SUMMARY TABLE: What You'll Pay

| Component | Free Option | Budget | Professional |
|-----------|------------|--------|--------------|
| Stock Data | Alpaca free | Alpha Vantage $50 | Polygon.io $300 |
| News | None | Finnhub $50 | Benzinga $500 |
| Broker | Alpaca | Alpaca | Interactive Brokers |
| Infrastructure | Local machine | DigitalOcean $6 | AWS $200 |
| **TOTAL** | **$0** | **~$100-150** | **$600-1000** |

The free option works for paper trading. The budget option works for live trading with small accounts. The professional option is for serious, full-time trading.

