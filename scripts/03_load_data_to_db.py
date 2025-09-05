# -*- coding: utf-8 -*-
"""
이 스크립트는 정제된 CSV 파일의 데이터를 읽어와 PostgreSQL 데이터베이스의 'products' 테이블로 이전합니다.
Pandas를 사용하여 데이터를 읽고, psycopg2를 통해 데이터베이스에 효율적으로 대량 삽입(bulk insert)합니다.
스크립트를 여러 번 실행해도 문제가 없도록, 실행 시마다 테이블을 비우고 다시 로드합니다.
"""
import pandas as pd
import psycopg2
import os
import io

# 데이터베이스 연결 정보 (core/database.py와 동일하게 유지)
DB_NAME = "market_insights"
DB_USER = "user"
DB_PASSWORD = "password"
DB_HOST = "localhost"
DB_PORT = "5432"

def load_data_to_db():
    """
    CSV 데이터를 데이터베이스에 로드하는 메인 함수.
    """
    try:
        # 1. 데이터베이스 연결
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
        cur = conn.cursor()
        print("데이터베이스 연결 성공.")

        # 2. 테이블 비우기 (스크립트를 여러 번 실행 가능하도록)
        print("'products' 테이블을 비웁니다...")
        cur.execute("TRUNCATE TABLE products RESTART IDENTITY CASCADE")
        conn.commit()

        # 3. CSV 파일 읽기
        base_dir = '/Users/jinhochoi/Desktop/개발/Market_insights'
        csv_path = os.path.join(base_dir, 'data', 'amazon_products_sales_data_cleaned.csv')
        df = pd.read_csv(csv_path)
        print(f"'{csv_path}'에서 {len(df)}개의 행을 읽었습니다.")

        # 4. 데이터 준비 (스키마에 맞게 컬럼 선택 및 이름 변경)
        df['product_id'] = df['product_page_url'].str.extract(r'/dp/(\w+)')
        df.dropna(subset=['product_id'], inplace=True)
        
        df_to_load = df[[
            'product_id',
            'product_title',
            'product_category',
            'discounted_price',
            'product_rating',
            'total_reviews',
            'data_collected_at'
        ]].copy()

        df_to_load.rename(columns={
            'product_title': 'name',
            'product_category': 'category',
            'discounted_price': 'price',
            'product_rating': 'rating',
            'total_reviews': 'reviews_count',
            'data_collected_at': 'created_at'
        }, inplace=True)

        # 5. 중복된 product_id 제거
        initial_rows = len(df_to_load)
        df_to_load.drop_duplicates(subset=['product_id'], keep='first', inplace=True)
        final_rows = len(df_to_load)
        print(f"{initial_rows - final_rows}개의 중복된 상품 ID를 제거했습니다. 최종 {final_rows}개 상품을 로드합니다.")

        # 6. 효율적인 대량 삽입 (COPY 사용)
        buffer = io.StringIO()
        df_to_load.to_csv(buffer, index=False, header=False, sep='\t')
        buffer.seek(0)
        
        print("데이터 삽입을 시작합니다...")
        columns = ', '.join(df_to_load.columns)
        cur.copy_expert(f"COPY products({columns}) FROM STDIN WITH CSV DELIMITER E'\\t'", buffer)
        
        conn.commit()
        print(f"{len(df_to_load)}개의 행이 'products' 테이블에 성공적으로 삽입되었습니다.")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"오류: {error}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cur' in locals() and cur:
            cur.close()
        if 'conn' in locals() and conn:
            conn.close()
            print("데이터베이스 연결을 종료합니다.")

if __name__ == '__main__':
    load_data_to_db()
