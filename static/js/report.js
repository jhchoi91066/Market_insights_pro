class ReportPage {
    constructor(reportData) {
        this.reportData = reportData;
        this.allProducts = this.parseProductPrices(reportData.top_10_products || []);
        this.charts = {};
        this.priceRange = [0, 1000];
        this.currentSort = 'purchased_last_month';
        this.debouncedFilter = this.debounce(this.filterDataByPrice, 250);

        this.init();
    }

    init() {
        this.setupCharts();
        this.setupPriceSlider();
        this.setupSortSelector();
        this.updateDashboard(this.allProducts);
    }

    debounce(func, delay) {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    }

    parseProductPrices(products) {
        return products.map(p => {
            const priceStr = (p.discounted_price || '0').replace(/[^\d.]/g, '');
            p.numeric_price = parseFloat(priceStr) || 0;
            return p;
        });
    }

    setupPriceSlider() {
        const slider = document.getElementById('price-slider');
        if (!slider) return;

        const prices = this.allProducts.map(p => p.numeric_price).filter(p => p > 0);
        const minPrice = prices.length > 0 ? Math.floor(Math.min(...prices)) : 0;
        const maxPrice = prices.length > 0 ? Math.ceil(Math.max(...prices)) : 100;
        this.priceRange = [minPrice, maxPrice];

        noUiSlider.create(slider, {
            start: this.priceRange,
            connect: true,
            range: {
                'min': minPrice,
                'max': maxPrice
            },
            format: {
                to: value => `${Math.round(value)}`,
                from: value => Number(value.replace(', '))
            }
        });

        slider.noUiSlider.on('update', (values) => {
            const [min, max] = values.map(v => Number(v.replace(', ', '')));
            document.getElementById('price-slider-values').innerHTML = `Selected: <span class="font-semibold">${values[0]} - ${values[1]}</span>`;
            this.debouncedFilter(min, max);
        });
    }

    setupSortSelector() {
        const sortSelect = document.getElementById('sort-select');
        if (sortSelect) {
            sortSelect.addEventListener('change', (e) => {
                this.currentSort = e.target.value;
                this.filterDataByPrice(...this.priceRange); // Re-filter and sort
            });
        }
    }

    sortProducts(products) {
        const sortKey = this.currentSort;
        return [...products].sort((a, b) => {
            if (sortKey === 'numeric_price_asc') {
                return a.numeric_price - b.numeric_price;
            } else if (sortKey === 'numeric_price_desc') {
                return b.numeric_price - a.numeric_price;
            } else {
                // Default to descending for sales and rating
                return b[sortKey] - a[sortKey];
            }
        });
    }

    filterDataByPrice(min, max) {
        this.priceRange = [min, max];
        const filteredProducts = this.allProducts.filter(p => p.numeric_price >= min && p.numeric_price <= max);
        const sortedProducts = this.sortProducts(filteredProducts);
        this.updateDashboard(sortedProducts);
    }

    updateDashboard(products) {
        document.getElementById('filtered-product-count').textContent = `${products.length} of ${this.allProducts.length}`;
        this.renderTable(products);
        this.updateCharts(products);
    }

    renderTable(products) {
        const tableBody = document.getElementById('products-table-body');
        const noProductsMsg = document.getElementById('no-products-message');
        if (!tableBody || !noProductsMsg) return;

        tableBody.innerHTML = '';
        if (products.length === 0) {
            noProductsMsg.classList.remove('hidden');
            return;
        }
        noProductsMsg.classList.add('hidden');

        products.forEach((p, index) => {
            const row = `
                <tr>
                    <td><span class="rank">${index + 1}</span></td>
                    <td class="max-w-xs"><div class="font-medium text-gray-900 dark:text-white truncate">${p.product_title}</div></td>
                    <td><span class="font-semibold text-gray-900 dark:text-white">${p.discounted_price}</span></td>
                    <td>
                        <div class="flex items-center">
                            <span class="text-sm font-medium text-gray-900 dark:text-white">${p.product_rating}</span>
                            <div class="flex ml-1">${[...Array(5)].map((_, i) => `<svg class="w-4 h-4 ${i < Math.round(p.product_rating) ? 'text-yellow-400' : 'text-gray-300 dark:text-gray-600'}" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>`).join('')}</div>
                        </div>
                    </td>
                    <td><span class="badge badge-primary">${p.purchased_last_month}+/mo</span></td>
                    <td>${p.is_prime ? '<span class="badge badge-success">📦 Prime</span>' : '<span class="text-gray-400 text-sm">Standard</span>'}</td>
                </tr>
            `;
            tableBody.innerHTML += row;
        });
    }

    setupCharts() {
        Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
        const isDarkMode = document.documentElement.classList.contains('dark');
        Chart.defaults.color = isDarkMode ? '#9CA3AF' : '#6B7280';

        // Competition Overview Chart
        const competitionCtx = document.getElementById('competitionChart').getContext('2d');
        this.charts.competition = new Chart(competitionCtx, {
            type: 'doughnut',
            data: {
                labels: ['Prime Products', 'Standard Products'],
                datasets: [{
                    data: [this.reportData.prime_count, this.reportData.competitor_count - this.reportData.prime_count],
                    backgroundColor: ['#10B981', '#6B7280'],
                    borderWidth: 0, hoverOffset: 4
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
        });

        // Market Share Chart
        const marketShareCtx = document.getElementById('marketShareChart').getContext('2d');
        this.charts.marketShare = new Chart(marketShareCtx, {
            type: 'bar',
            data: { labels: [], datasets: [{ label: 'Monthly Sales', data: [], backgroundColor: '#3B82F6', borderRadius: 4 }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
        });
    }

    updateCharts(products) {
        // Update Market Share Chart with top 5 filtered products
        const top5 = products.sort((a, b) => b.purchased_last_month - a.purchased_last_month).slice(0, 5);
        this.charts.marketShare.data.labels = top5.map(p => p.product_title.substring(0, 15) + '...');
        this.charts.marketShare.data.datasets[0].data = top5.map(p => p.purchased_last_month);
        this.charts.marketShare.update();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const reportData = {
        keyword: '{{ report.keyword }}',
        difficulty_score: {{ report.difficulty_score }},
        competitor_count: {{ report.competitor_count }},
        prime_count: {{ report.prime_count or 0 }},
        prime_percentage: {{ report.prime_percentage or 0 }},
        market_saturation_percentage: {{ report.market_saturation_percentage }},
        top_10_products: {{ report.top_10_products|tojson|safe }},
        rating_by_price_bin: {{ report.rating_by_price_bin|tojson|safe if report.rating_by_price_bin else '{}' }}
    };
    new ReportPage(reportData);
});