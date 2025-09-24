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
            p.numeric_price = p.discounted_price || 0;
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
        console.log(`Sorting by: ${sortKey}`); // For debugging
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
                    <td><span class="font-medium text-gray-700 dark:text-gray-300">${p.brand || 'N/A'}</span></td>
                </tr>
            `;
            tableBody.innerHTML += row;
        });
    }

    setupCharts() {
        Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
        const isDarkMode = document.documentElement.classList.contains('dark');
        Chart.defaults.color = isDarkMode ? '#9CA3AF' : '#6B7280';

        // Market Share Chart
        const marketShareCtx = document.getElementById('marketShareChart').getContext('2d');
        this.charts.marketShare = new Chart(marketShareCtx, {
            type: 'bar',
            data: { labels: [], datasets: [{ label: 'Monthly Sales', data: [], backgroundColor: '#3B82F6', borderRadius: 4 }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
        });

        // ML Predictions Chart (only if predictions are available)
        if (this.reportData.has_ml_predictions && this.reportData.ml_predictions) {
            this.setupMLPredictionsChart();
        }
    }

    setupMLPredictionsChart() {
        const mlChartCtx = document.getElementById('mlPredictionsChart');
        if (!mlChartCtx) return;

        const predictions = this.reportData.ml_predictions;
        const isDarkMode = document.documentElement.classList.contains('dark');

        // 차트 데이터 준비
        const labels = predictions.map(p => p.product_title.substring(0, 20) + '...');
        const actualPrices = predictions.map(p => p.actual_price);
        const predictedPrices = predictions.map(p => p.predicted_price);

        this.charts.mlPredictions = new Chart(mlChartCtx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Actual Price',
                    data: actualPrices,
                    backgroundColor: isDarkMode ? 'rgba(75, 192, 192, 0.6)' : 'rgba(34, 197, 94, 0.6)',
                    borderColor: isDarkMode ? 'rgba(75, 192, 192, 1)' : 'rgba(34, 197, 94, 1)',
                    borderWidth: 1
                }, {
                    label: 'Predicted Price',
                    data: predictedPrices,
                    backgroundColor: isDarkMode ? 'rgba(147, 51, 234, 0.6)' : 'rgba(168, 85, 247, 0.6)',
                    borderColor: isDarkMode ? 'rgba(147, 51, 234, 1)' : 'rgba(168, 85, 247, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                const prediction = predictions[context.dataIndex];
                                const accuracy = (100 - prediction.prediction_accuracy).toFixed(1);

                                if (label === 'Predicted Price') {
                                    return `${label}: $${value.toFixed(2)} (Accuracy: ${accuracy}%)`;
                                }
                                return `${label}: $${value.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: isDarkMode ? 'rgba(75, 85, 99, 0.3)' : 'rgba(229, 231, 235, 0.8)'
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: isDarkMode ? 'rgba(75, 85, 99, 0.3)' : 'rgba(229, 231, 235, 0.8)'
                        },
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toFixed(2);
                            }
                        }
                    }
                }
            }
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
    try {
        const rawReportData = document.getElementById('report-data').textContent;
        const reportData = JSON.parse(rawReportData);
        new ReportPage(reportData);
    } catch (e) {
        console.error("Failed to parse report data:", e);
    }
});