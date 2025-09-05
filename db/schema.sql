-- 핵심 테이블 설계
CREATE TABLE products (
    product_id VARCHAR PRIMARY KEY,
    name TEXT,
    category VARCHAR(100),
    price DECIMAL(10,2),
    rating DECIMAL(3,2),
    reviews_count INT,
    brand VARCHAR(100),
    created_at TIMESTAMP
);

CREATE TABLE market_analysis (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100),
    analysis_type VARCHAR(50),
    data JSONB,
    created_at TIMESTAMP
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR UNIQUE,
    company_name VARCHAR(100),
    subscription_tier VARCHAR(20),
    created_at TIMESTAMP
);
