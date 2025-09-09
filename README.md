# 🚀 Amazon Market Insights Pro

A powerful Amazon market analysis tool that provides comprehensive insights into product competition, market saturation, and entry barriers.

## 📋 Overview

Amazon Market Insights Pro automatically scrapes Amazon product data and generates detailed market analysis reports to help businesses make informed decisions about product entry strategies.

## ✨ Features

- **🔍 Real-time Amazon Scraping**: Automated data collection from Amazon search results
- **📊 Market Analysis**: 
  - Competition density analysis
  - Market saturation calculations
  - Entry barrier scoring (0-10 scale)
  - Prime shipping percentage tracking
- **💰 Price & Sales Intelligence**: 
  - USD pricing analysis
  - Sales volume tracking (monthly purchases)
  - Top 10 products ranking
- **🛡️ Advanced Bot Detection Evasion**:
  - Dynamic User-Agent rotation
  - Human-like browsing patterns
  - Session warming and random delays
- **🔒 Concurrency Control**: Queue system prevents Amazon blocking
- **🌐 Web Interface**: User-friendly Bootstrap-based UI

## 🛠️ Technical Stack

- **Backend**: FastAPI, Python 3.11+
- **Database**: SQLite with SQLAlchemy ORM
- **Web Scraping**: Playwright (Chromium)
- **Frontend**: Bootstrap 5, Jinja2 Templates
- **HTML Parsing**: BeautifulSoup4

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Node.js (for Playwright browser installation)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Market_insights
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers:**
   ```bash
   playwright install chromium
   ```

4. **Run the application:**
   ```bash
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

5. **Access the web interface:**
   ```
   http://localhost:8000
   ```

## 📖 Usage

### Web Interface

1. Open your browser and navigate to `http://localhost:8000`
2. Enter a product keyword (e.g., "wireless mouse", "bluetooth headphones")
3. Click "Start Analysis" and wait for results (1-2 minutes)
4. Review the comprehensive market analysis report

### API Usage

**Analyze a product category:**
```bash
curl -X POST http://localhost:8000/report \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "keyword=wireless mouse"
```

## 📊 Analysis Features

### Market Entry Barrier Score (0-10)
- **0-3**: Low competition, easy entry
- **4-6**: Moderate competition
- **7-10**: High competition, difficult entry

**Scoring Components:**
- **Competition Density** (0-4 points): Number of competing products
- **Quality Expectations** (0-3 points): Average customer ratings
- **Entry Barriers** (0-3 points): Review counts and sales volumes

### Market Saturation Analysis
- Estimates total market size based on Amazon category data
- Calculates TOP 10 products' market share
- Provides realistic saturation percentages (15-60% range)

### Competition Intelligence
- Total competing products count
- Prime shipping availability percentage
- Price distribution analysis
- Top performers identification

## 🔧 Configuration

### Environment Variables

Create a `.env` file (optional):
```env
# Database settings
DATABASE_URL=sqlite:///data/market_insights.db

# Scraping settings
MAX_PRODUCTS=100
SCRAPING_DELAY=5

# Server settings
HOST=127.0.0.1
PORT=8000
```

### Customization

**Adjust scraping parameters in `main.py`:**
```python
# Change maximum products to scrape
db_result = await scraper.scrape_and_save_to_db(keyword, max_products=100)

# Change minimum data threshold
if existing_count < 30:  # Requires 30+ products before skipping scraping
```

**Modify analysis logic in `core/analyzer_v2.py`:**
```python
# Adjust market size estimates
category_multipliers = {
    'electronics': 10000,
    'clothing': 20000,
    'home': 15000,
    'default': 8000
}
```

## 🏗️ Architecture

```
Market_insights/
├── core/
│   ├── scraper.py          # Amazon scraping logic
│   ├── analyzer_v2.py      # Market analysis algorithms
│   ├── models.py           # Database models
│   └── database.py         # Database management
├── templates/              # HTML templates
│   ├── index.html         # Main search page
│   ├── report.html        # Analysis results
│   ├── error.html         # Error handling
│   └── base.html          # Base template
├── static/                # CSS, JS, images
│   └── js/main.js         # Frontend JavaScript
├── data/                  # SQLite database storage
├── docs/                  # Documentation
│   └── progress_v2.md     # Development progress
├── main.py               # FastAPI application
└── requirements.txt      # Python dependencies
```

## 📈 Performance

### Scraping Performance
- **Data Collection**: 100 products in ~2-3 minutes
- **Analysis Speed**: Real-time calculation (<1 second)
- **Success Rate**: 95%+ with advanced bot evasion
- **Concurrency**: Queue system handles multiple simultaneous requests

### Bot Detection Evasion
- Dynamic User-Agent rotation (5 different profiles)
- Human-like delays (7-16 seconds with randomization)
- Session warming with natural browsing patterns
- Advanced browser fingerprint masking

## 🚨 Important Notes

### Legal Compliance
- This tool is for educational and research purposes
- Respect Amazon's robots.txt and terms of service
- Use reasonable delays between requests
- Do not overload Amazon's servers

### Rate Limiting
- Built-in concurrency control (one analysis at a time)
- Automatic retry logic with exponential backoff
- Random delays to mimic human behavior

### Data Accuracy
- Market analysis is based on sampled data (100 products max)
- Saturation percentages are estimates based on Amazon market size
- Results should be used as guidelines, not absolute metrics

## 🛡️ Error Handling

The system includes comprehensive error handling:

- **Amazon Error Pages**: Automatic detection and user-friendly messages
- **Browser Crashes**: Graceful recovery with detailed logging
- **Network Issues**: Retry logic with timeout management
- **Data Validation**: Input sanitization and format checking

## 📝 Logging

Debug logs are saved to `debug_log.txt` with detailed information:
- Scraping progress and timing
- Error messages and stack traces
- Analysis calculation steps
- Performance metrics

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Playwright](https://playwright.dev/) for reliable browser automation
- [FastAPI](https://fastapi.tiangolo.com/) for the modern web framework
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for HTML parsing
- [Bootstrap](https://getbootstrap.com/) for responsive UI components

## 📞 Support

For issues, questions, or feature requests:
- Create an issue in the GitHub repository
- Check the `docs/progress_v2.md` for development notes
- Review error logs in `debug_log.txt` for troubleshooting

---

**⚠️ Disclaimer**: This tool is for educational purposes only. Users are responsible for complying with Amazon's terms of service and applicable laws. Use responsibly and ethically.